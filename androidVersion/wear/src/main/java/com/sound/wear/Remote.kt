package com.sound.wear

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.AudioManager
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Hesabın diğer SOUND cihazları (devices.py, Supabase Realtime): saat de bir cihazdır. PC'de çalanı görür ve kumanda eder
 * (çal/duraklat, geç, ses), çalmayı saate alır ya da başka cihaza verir; saatte çalan şarkı da PC'de görünür ve oradan
 * kumanda edilir. Kanal anahtarını telefon verir (watch_lists "devices"); sonrası telefonsuz da çalışır.
 */
object Remote {
    private val main = Handler(Looper.getMainLooper())
    private val listeners = mutableSetOf<() -> Unit>()
    private lateinit var app: Context

    @Volatile var connected = false
        private set
    var devices: List<JSONObject> = emptyList()
        private set
    private val nps = mutableMapOf<String, JSONObject>()  // cihaz -> son durum (+ "rx": alındığı an)
    private var startedKey: String? = null
    private var seq = System.currentTimeMillis()
    private var qv = 0
    private var lastSig = ""
    private var live = false  // saat bu açılışta çaldı mı (çalmadıysa "hello"ya yanıt vermez)

    fun listen(listener: () -> Unit) { listeners += listener }
    fun unlisten(listener: () -> Unit) { listeners -= listener }
    private fun changed() = listeners.toList().forEach { it() }

    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences("sound", Context.MODE_PRIVATE)

    /** Saatin cihaz kimliği (kalıcı). */
    fun me(context: Context): String {
        val p = prefs(context)
        return p.getString("device_id", null) ?: java.util.UUID.randomUUID().toString().replace("-", "").take(12).also {
            p.edit().putString("device_id", it).apply()
        }
    }

    /** Diğer cihazlarda görünecek ad. Samsung saatlerde sistem adı model kodudur (SM-R950): "Galaxy Watch" yazılır. */
    private fun name(context: Context): String {
        val name = runCatching { Settings.Global.getString(context.contentResolver, Settings.Global.DEVICE_NAME) }.getOrNull()
            ?.replace(Regex("\\s*\\([^)]*\\)$"), "")?.trim()
        return when {
            name.isNullOrBlank() || name.equals(android.os.Build.MODEL, ignoreCase = true) || name.startsWith("SM-") ->
                if (android.os.Build.MANUFACTURER.equals("samsung", ignoreCase = true)) "Galaxy Watch" else "Saat"
            else -> name
        }
    }

    /** Telefon yeni anahtar gönderdi (ya da açılışta saklı olan). */
    fun setKey(context: Context, key: String) {
        if (key.isNotEmpty() && prefs(context).getString("devices_key", "") != key) prefs(context).edit().putString("devices_key", key).apply()
        start(context)
    }

    fun start(context: Context) {
        if (!::app.isInitialized) app = context.applicationContext
        val key = prefs(context).getString("devices_key", "") ?: ""
        if (key.isEmpty() || key == startedKey) return
        startedKey = key
        val me = me(context)
        val name = name(context)
        Py.pool.execute {
            Py.raw(app, "devices_start", key, me, name)
            android.util.Log.i("SOUND", "Cihaz kanalı başlatıldı ($name)")
        }
    }

    val available get() = startedKey != null

    // ---------- Python'dan gelen olaylar ----------

    @JvmStatic fun event(json: String) {
        val e = runCatching { JSONObject(json) }.getOrNull() ?: return
        main.post { handle(e) }
    }

    private fun handle(e: JSONObject) {
        if (e.optString("type") == "status") {
            val st = e.optJSONObject("status") ?: JSONObject()
            connected = st.optBoolean("connected")
            val me = st.optString("me")
            val list = st.optJSONArray("devices") ?: JSONArray()
            devices = (0 until list.length()).map { list.getJSONObject(it) }.filter { it.optString("id") != me }
            nps.keys.retainAll(devices.map { it.optString("id") }.toSet())
            if (connected) localChanged(force = true)
            changed()
            return
        }
        val from = e.optString("from")
        val data = e.optJSONObject("data") ?: JSONObject()
        when (e.optString("kind")) {
            "np" -> {
                val old = nps[from]
                if (old != null && data.optLong("seq") <= old.optLong("seq") && data.optLong("seq") != 0L) return
                if (old != null && !data.has("queue") && old.has("queue")) { data.put("queue", old.get("queue")); data.put("pos", old.opt("pos")) }
                nps[from] = data.put("rx", System.currentTimeMillis())
                changed()
            }
            "hello" -> if (live) publish(full = true)
            "cmd" -> command(data)
            "transfer" -> receive(data)
        }
    }

    // ---------- diğer cihazları kumanda ----------

    fun np(id: String): JSONObject? = nps[id]

    /** O cihazda şarkının şu anki konumu (sn). */
    fun position(np: JSONObject): Double {
        val at = np.optDouble("at", 0.0)
        if (!np.optBoolean("playing")) return at
        val dur = np.optJSONObject("track")?.optDouble("duration", 0.0) ?: 0.0
        val now = at + (System.currentTimeMillis() - np.optLong("rx")) / 1000.0
        return if (dur > 0) now.coerceAtMost(dur) else now
    }

    fun deviceName(id: String) = devices.firstOrNull { it.optString("id") == id }?.optString("name") ?: "Diğer cihaz"
    fun deviceKind(id: String) = devices.firstOrNull { it.optString("id") == id }?.optString("kind") ?: "pc"

    fun send(kind: String, data: JSONObject, to: String = "") {
        if (!::app.isInitialized) return
        Py.pool.execute { Py.raw(app, "devices_send", kind, data.toString(), to) }
    }

    fun cmd(to: String, cmd: String, extra: JSONObject.() -> Unit = {}) = send("cmd", JSONObject().put("cmd", cmd).apply(extra), to)

    /** Kumandada düğmeye basılınca hemen görünsün (cihazın asıl durumu birazdan gelir). */
    fun guessPlaying(id: String, playing: Boolean) {
        nps[id]?.let { np ->
            np.put("at", position(np)).put("rx", System.currentTimeMillis()).put("playing", playing)
            changed()
        }
    }

    fun setVolume(id: String, v: Double) {
        nps[id]?.put("volume", v)
        cmd(id, "volume") { put("v", v) }
    }

    // ---------- saat de bir cihaz: durumunu yayınla, komut al ----------

    /** LocalPlayer değişince: çalan şarkı / durum değiştiyse kanala yaz. */
    fun localChanged(force: Boolean = false) {
        if (!::app.isInitialized || !connected) return
        if (LocalPlayer.playing) live = true
        if (!live || !LocalPlayer.hasTrack) return
        val sig = "${LocalPlayer.current?.optString("id")}|${LocalPlayer.playing}|${LocalPlayer.queue.size}"
        if (sig == lastSig && !force) return
        if (sig.substringAfterLast('|') != lastSig.substringAfterLast('|')) qv++
        lastSig = sig
        publish(full = true)
    }

    private fun publish(full: Boolean) {
        val track = LocalPlayer.current ?: return
        val data = JSONObject()
            .put("seq", ++seq)
            .put("playing", LocalPlayer.playing)
            .put("at", LocalPlayer.position())
            .put("ts", System.currentTimeMillis())
            .put("qv", qv)
            .put("track", Lib.slim(track))
            .put("shuffle", false)
            .put("repeat", "off")
            .put("volume", streamVolume())
        if (full) {
            val start = maxOf(0, LocalPlayer.index - 1)
            val queue = JSONArray()
            LocalPlayer.queue.drop(start).take(100).forEach { queue.put(Lib.slim(it)) }
            data.put("queue", queue).put("pos", LocalPlayer.index - start)
        }
        send("np", data)
    }

    private fun streamVolume(): Double {
        val am = app.getSystemService(AudioManager::class.java)
        return am.getStreamVolume(AudioManager.STREAM_MUSIC).toDouble() / am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
    }

    /** PC (ya da telefon) saatte çalanı kumanda ediyor. */
    private fun command(c: JSONObject) {
        if (!LocalPlayer.hasTrack) return
        when (c.optString("cmd")) {
            "toggle" -> LocalPlayer.toggle(app)
            "play" -> if (!LocalPlayer.playing) LocalPlayer.play(app)
            "pause" -> if (LocalPlayer.playing) LocalPlayer.pause()
            "next" -> LocalPlayer.next(app)
            "previous" -> LocalPlayer.previous(app)
            "seek" -> LocalPlayer.seek(c.optDouble("at", 0.0))
            "volume" -> {
                val am = app.getSystemService(AudioManager::class.java)
                val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
                am.setStreamVolume(AudioManager.STREAM_MUSIC, (c.optDouble("v", 0.5) * max).toInt().coerceIn(0, max), 0)
            }
            "jump" -> LocalPlayer.queue.indexOfFirst { it.optString("id") == c.optString("id") }.takeIf { it >= 0 }?.let { LocalPlayer.jump(app, it) }
            "playlist" -> c.optJSONArray("tracks")?.let { LocalPlayer.playList(app, it, c.optInt("index")) }
            "handoff" -> transferTo(app, c.optString("to"))
        }
        publish(full = true)
    }

    /** Başka cihazdan çalma saate geçti. */
    private fun receive(d: JSONObject) {
        val queue = d.optJSONArray("queue") ?: return
        Where.set(app, "watch")
        live = true
        LocalPlayer.playList(app, queue, d.optInt("pos"), d.optDouble("at", 0.0))
        Toast.makeText(app, "Çalma saate geçti", Toast.LENGTH_SHORT).show()
        changed()
    }

    /** Saatte çalanı başka cihaza ver (sıra ve konumla). */
    fun transferTo(context: Context, to: String) {
        if (to.isEmpty() || !LocalPlayer.hasTrack) return
        val start = maxOf(0, LocalPlayer.index - 1)
        val queue = JSONArray()
        LocalPlayer.queue.drop(start).take(100).forEach { queue.put(Lib.slim(it)) }
        send("transfer", JSONObject().put("queue", queue).put("pos", LocalPlayer.index - start).put("at", LocalPlayer.position())
            .put("shuffle", false).put("repeat", "off"), to)
        LocalPlayer.pause()
        live = false
    }

    // ---------- kapak ----------

    private var artId: String? = null
    var art: Bitmap? = null
        private set

    fun artFor(id: String): Bitmap? {
        if (id == artId) return art
        artId = id
        art = null
        Py.pool.execute {
            val bitmap = runCatching {
                val connection = URL("https://i.ytimg.com/vi/$id/hqdefault.jpg").openConnection() as HttpURLConnection
                connection.connectTimeout = 8000
                connection.readTimeout = 8000
                connection.inputStream.use { BitmapFactory.decodeStream(it) }?.let { b ->
                    val side = minOf(b.width, b.height * 3 / 4)
                    Bitmap.createBitmap(b, (b.width - side) / 2, (b.height - side) / 2, side, side)
                }
            }.getOrNull()
            main.post { if (artId == id) { art = bitmap; changed() } }
        }
        return null
    }
}
