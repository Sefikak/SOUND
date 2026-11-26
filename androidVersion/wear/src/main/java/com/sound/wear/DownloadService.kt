package com.sound.wear

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

/**
 * Saate indirilen listeler (internetsiz dinlemek için). Kayıt: anahtar → {title, tracks}. Dosyalar Python'un offline/
 * klasöründe; bir şarkı birden çok listede olabilir, son liste silinince dosya da silinir.
 */
object Offline {
    private val main = Handler(Looper.getMainLooper())
    private val listeners = mutableSetOf<() -> Unit>()
    /** İndirilmekte olan liste: anahtar → (inen, toplam) */
    val progress = mutableMapOf<String, Pair<Int, Int>>()
    @Volatile private var idsCache: Set<String>? = null

    fun listen(listener: () -> Unit) { listeners += listener }
    fun unlisten(listener: () -> Unit) { listeners -= listener }
    fun changed() = main.post { listeners.toList().forEach { it() } }

    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences("sound", Context.MODE_PRIVATE)

    fun all(context: Context): JSONObject = runCatching { JSONObject(prefs(context).getString("offline", "{}")!!) }.getOrDefault(JSONObject())

    fun list(context: Context, key: String): JSONObject? = all(context).optJSONObject(key)

    fun has(context: Context, key: String) = all(context).has(key)

    /** Saatte dosyası olan şarkı kimlikleri (watch_main.OFFLINE_DIR: files/sound/offline/<kimlik>.webm). */
    fun ids(context: Context): Set<String> {
        idsCache?.let { return it }
        val files = context.applicationContext.filesDir.resolve("sound/offline").listFiles() ?: emptyArray()
        return files.filter { it.name.endsWith(".webm") && it.length() > 0 }.map { it.name.removeSuffix(".webm") }.toSet().also { idsCache = it }
    }

    fun forgetIds() { idsCache = null }

    /** Listeyi saate indir (Wi-Fi'da, arka planda). Liste sonradan telefonda değişirse yeniden indirilince güncellenir. */
    fun add(context: Context, key: String, title: String, tracks: JSONArray) {
        val all = all(context)
        all.put(key, JSONObject().put("title", title).put("tracks", tracks).put("at", System.currentTimeMillis()))
        prefs(context).edit().putString("offline", all.toString()).apply()
        changed()
        context.startForegroundService(Intent(context, DownloadService::class.java).putExtra("key", key))
    }

    fun remove(context: Context, key: String) {
        val all = all(context)
        val removed = all.optJSONObject(key) ?: return
        all.remove(key)
        prefs(context).edit().putString("offline", all.toString()).apply()
        progress.remove(key)
        val keep = mutableSetOf<String>()
        for (k in all.keys()) {
            val a = all.getJSONObject(k).optJSONArray("tracks") ?: continue
            for (i in 0 until a.length()) keep += a.getJSONObject(i).optString("id")
        }
        val tracks = removed.optJSONArray("tracks") ?: JSONArray()
        val app = context.applicationContext
        Py.pool.execute {
            for (i in 0 until tracks.length()) {
                val id = tracks.getJSONObject(i).optString("id")
                if (id !in keep) Py.raw(app, "forget", id)
            }
            forgetIds()
            changed()
        }
        changed()
    }

    /** Tüm indirilenler tek liste olarak (internetsizken karışık çalmak için). */
    fun allTracks(context: Context): JSONArray {
        val out = JSONArray()
        val seen = mutableSetOf<String>()
        val have = ids(context)
        val all = all(context)
        for (k in all.keys()) {
            val a = all.getJSONObject(k).optJSONArray("tracks") ?: continue
            for (i in 0 until a.length()) { val t = a.getJSONObject(i); val id = t.optString("id"); if (id in have && seen.add(id)) out.put(t) }
        }
        return out
    }
}

/** Saate indirme: listedeki şarkılar sırayla iner, bildirimde ilerleme görünür. Wi-Fi istenir (yoksa var olan bağlantı). */
class DownloadService : Service() {
    private val worker = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private var pending = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel("downloads", "Saate indirme", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) })
        foreground("Saate indiriliyor…", 0, 0)
        Net.acquire(this)
    }

    private fun foreground(text: String, done: Int, total: Int) {
        val open = PendingIntent.getActivity(this, 1, Intent(this, LibraryActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(this, "downloads")
            .setSmallIcon(R.drawable.ic_download)
            .setContentTitle("SOUND")
            .setContentText(text)
            .setProgress(total, done, total == 0)
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(open)
            .build()
        ServiceCompat.startForeground(this, 8, notification, if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        foreground("Saate indiriliyor…", 0, 0)
        val key = intent?.getStringExtra("key") ?: return START_NOT_STICKY.also { finishIfIdle() }
        pending++
        worker.execute {
            runCatching { download(key) }
            main.post { pending--; finishIfIdle() }
        }
        return START_NOT_STICKY
    }

    private fun download(key: String) {
        val list = Offline.list(this, key) ?: return
        val title = list.optString("title")
        val tracks = list.optJSONArray("tracks") ?: return
        Thread.sleep(1500)  // Wi-Fi bağlansın
        var done = 0
        var failedNet = 0
        for (i in 0 until tracks.length()) {
            if (!Offline.has(this, key)) break  // liste bu arada silindi
            Offline.progress[key] = done to tracks.length()
            Offline.changed()
            main.post { foreground("$title · ${done + 1}/${tracks.length()}", done, tracks.length()) }
            val result = Py.call(this, "fetch", tracks.getJSONObject(i).toString(), true)
            if (result.has("path")) { done++; failedNet = 0 }
            else if (result.optBoolean("network") && ++failedNet >= 3) break  // internet gitti: kalanlar sonraki sefere
        }
        Offline.progress.remove(key)
        Offline.forgetIds()
        Offline.changed()
    }

    private fun finishIfIdle() {
        if (pending > 0) return
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        Net.release(this)
        worker.shutdownNow()
        super.onDestroy()
    }
}
