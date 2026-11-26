package com.sound.wear

import android.app.Activity
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.widget.Toast
import androidx.core.app.NotificationCompat
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

/**
 * Saat uygulaması kendini günceller: GitHub'daki update/wear.json'a (mobile dalı) 6 saatte bir bakar, yeni sürümü indirir,
 * SHA-256 ile doğrular ve "Yükle" denince sistem kurulum onayını açar. Android onaysız kurulum ve farklı imzalı güncelleme kabul etmez.
 */
object Updater {
    private const val MANIFEST = "https://raw.githubusercontent.com/Sefikak/SOUND/mobile/update/wear.json"
    private const val EVERY = 6 * 3600 * 1000L
    private val main = Handler(Looper.getMainLooper())
    private val listeners = mutableSetOf<() -> Unit>()
    @Volatile private var running = false

    /** İnmiş ve doğrulanmış güncelleme: sürüm adı (yoksa null). */
    var ready: String? = null
        private set

    fun listen(listener: () -> Unit) { listeners += listener }
    fun unlisten(listener: () -> Unit) { listeners -= listener }

    private fun apk(context: Context) = context.applicationContext.cacheDir.resolve("update.apk")
    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences("sound", Context.MODE_PRIVATE)

    private fun installedCode(context: Context): Long =
        context.packageManager.getPackageInfo(context.packageName, 0).longVersionCode

    fun check(context: Context, force: Boolean = false) {
        val app = context.applicationContext
        val prefs = prefs(app)
        // önceki açılışta inmiş güncelleme hâlâ yeni mi
        val savedCode = prefs.getLong("update_code", 0)
        if (savedCode > installedCode(app) && apk(app).exists()) ready = prefs.getString("update_name", null)
        else if (savedCode != 0L && savedCode <= installedCode(app)) { apk(app).delete(); prefs.edit().remove("update_code").apply() }
        if (running || (!force && System.currentTimeMillis() - prefs.getLong("update_checked", 0) < EVERY)) return
        running = true
        Thread {
            try { run(app) } catch (e: Exception) { Log.w("SOUND", "Güncelleme denetlenemedi", e) } finally { running = false }
        }.start()
    }

    private fun run(app: Context) {
        val info = JSONObject(get(manifest(app)).decodeToString())
        prefs(app).edit().putLong("update_checked", System.currentTimeMillis()).apply()
        val code = info.getLong("versionCode")
        if (code <= installedCode(app)) return
        val file = apk(app)
        if (!(file.exists() && sha(file.readBytes()) == info.getString("sha256"))) {
            Net.acquire(app)
            try {
                val bytes = get(info.getString("url"))
                if (sha(bytes) != info.getString("sha256")) throw IllegalStateException("SHA-256 tutmadı")
                file.writeBytes(bytes)
            } finally { Net.release(app) }
        }
        prefs(app).edit().putLong("update_code", code).putString("update_name", info.optString("versionName")).apply()
        ready = info.optString("versionName")
        main.post { listeners.toList().forEach { it() } }
        notify(app)
    }

    /** debug derlemede başka bir adres denenebilir (adb: --es updurl http://...). */
    private fun manifest(app: Context): String {
        val debug = app.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0
        return prefs(app).getString("update_url", null)?.takeIf { debug } ?: MANIFEST
    }

    private fun get(url: String): ByteArray {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = 15000
        connection.readTimeout = 60000
        connection.setRequestProperty("Cache-Control", "no-cache")
        return connection.inputStream.use { it.readBytes() }
    }

    private fun sha(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    private fun notify(app: Context) {
        val nm = app.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel("update", "Güncelleme", NotificationManager.IMPORTANCE_DEFAULT))
        val open = PendingIntent.getActivity(app, 3, Intent(app, LibraryActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        runCatching {
            nm.notify(9, NotificationCompat.Builder(app, "update")
                .setSmallIcon(R.drawable.ic_download)
                .setContentTitle("SOUND güncellemesi hazır")
                .setContentText("Sürüm $ready · Kitaplık'tan yükle")
                .setContentIntent(open)
                .setAutoCancel(true)
                .build())
        }
    }

    /** Kur: izin yoksa "bilinmeyen uygulamaları yükle" ayarı açılır; varsa sistem onay ekranı. */
    fun install(activity: Activity) {
        val file = apk(activity)
        if (ready == null || !file.exists()) return
        if (!activity.packageManager.canRequestPackageInstalls()) {
            Toast.makeText(activity, "SOUND'a uygulama yükleme izni ver, sonra yeniden dokun", Toast.LENGTH_LONG).show()
            runCatching { activity.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${activity.packageName}"))) }
            return
        }
        val installer = activity.packageManager.packageInstaller
        val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
            setAppPackageName(activity.packageName)
        }
        val id = installer.createSession(params)
        installer.openSession(id).use { session ->
            session.openWrite("sound.apk", 0, file.length()).use { out -> file.inputStream().use { it.copyTo(out) }; session.fsync(out) }
            val intent = Intent(activity, InstallReceiver::class.java)
            val pending = PendingIntent.getBroadcast(activity, id, intent, PendingIntent.FLAG_MUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            session.commit(pending.intentSender)
        }
    }
}

/** Kurulum sonucu: onay gerekiyorsa sistemin onay ekranını aç. */
class InstallReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                @Suppress("DEPRECATION") val confirm = intent.getParcelableExtra<Intent>(Intent.EXTRA_INTENT) ?: return
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                runCatching { context.startActivity(confirm) }
                // ekran kapalıysa ya da SOUND öndeyken değilse Android onay ekranını açmaz: bildirimden açılsın
                val nm = context.getSystemService(NotificationManager::class.java)
                nm.createNotificationChannel(NotificationChannel("update", "Güncelleme", NotificationManager.IMPORTANCE_DEFAULT))
                val open = PendingIntent.getActivity(context, 4, confirm, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
                runCatching {
                    nm.notify(9, NotificationCompat.Builder(context, "update")
                        .setSmallIcon(R.drawable.ic_download)
                        .setContentTitle("SOUND güncellemesi")
                        .setContentText("Kurmak için dokun")
                        .setContentIntent(open)
                        .setAutoCancel(true)
                        .build())
                }
            }
            PackageInstaller.STATUS_SUCCESS -> {}
            else -> Toast.makeText(context, "Güncelleme kurulamadı: ${intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE) ?: ""}", Toast.LENGTH_LONG).show()
        }
    }
}
