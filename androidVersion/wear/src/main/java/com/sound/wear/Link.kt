package com.sound.wear

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import androidx.wear.tiles.TileService
import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.CapabilityClient
import com.google.android.gms.wearable.DataEvent
import com.google.android.gms.wearable.DataEventBuffer
import com.google.android.gms.wearable.DataItem
import com.google.android.gms.wearable.DataMapItem
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.WearableListenerService
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Telefondaki SOUND ile bağlantı (Wearable Data Layer). Telefon çalan şarkıyı /sound/now'a (kapakla), kitaplığı
 * /sound/lists'e yazar; saat komutları mesaj olarak gönderir (/sound/cmd, /sound/play, /sound/hello).
 */
object Link {
    const val NOW = "/sound/now"
    const val LISTS = "/sound/lists"
    private const val PHONE_CAPABILITY = "sound_phone"
    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    private val listeners = mutableSetOf<() -> Unit>()

    @Volatile var now: JSONObject? = null
    @Volatile var art: Bitmap? = null
    @Volatile var lists: JSONObject? = null
    /** null: henüz bilinmiyor, false: telefon bulunamadı (bağlı değil ya da SOUND yüklü değil) */
    @Volatile var phoneReachable: Boolean? = null
    @Volatile private var phoneNode: String? = null

    fun listen(listener: () -> Unit) { listeners += listener }
    fun unlisten(listener: () -> Unit) { listeners -= listener }
    private fun changed() = main.post { listeners.toList().forEach { it() } }

    /** Saklı veriyi oku, telefonu bul ve ona "buradayım" de (telefon taze durumu yeniden yazar). */
    fun start(context: Context) {
        val app = context.applicationContext
        io.execute {
            runCatching {
                val items = Tasks.await(Wearable.getDataClient(app).dataItems, 10, TimeUnit.SECONDS)
                try { for (item in items) read(app, item) } finally { items.release() }
            }
            findPhone(app)
            changed()
            if (sendNow(app, "/sound/hello", "")) sendLikes(app)
        }
    }

    /** Saatte yapılan beğenileri telefona gönder (telefon yoksa sonra). */
    fun flushLikes(context: Context) {
        val app = context.applicationContext
        io.execute { sendLikes(app) }
    }

    private fun sendLikes(app: Context) {
        val pending = Lib.takePending(app)
        val failed = mutableListOf<JSONObject>()
        for (i in 0 until pending.length()) {
            val item = pending.getJSONObject(i)
            if (failed.isNotEmpty() || !sendNow(app, "/sound/like", item.toString())) failed += item
        }
        Lib.putBack(app, failed)
    }

    private fun findPhone(app: Context) {
        runCatching {
            val info = Tasks.await(Wearable.getCapabilityClient(app).getCapability(PHONE_CAPABILITY, CapabilityClient.FILTER_REACHABLE), 10, TimeUnit.SECONDS)
            val node = info.nodes.firstOrNull { it.isNearby } ?: info.nodes.firstOrNull()
            phoneNode = node?.id
            phoneReachable = node != null
        }.onFailure { phoneReachable = false }
    }

    /** DataService ve açık ekranlardan: telefon yeni durum yazdı. */
    fun onData(context: Context, events: DataEventBuffer) {
        val app = context.applicationContext
        val items = events.filter { it.type == DataEvent.TYPE_CHANGED }.map { it.dataItem.freeze() }
        io.execute {
            items.forEach { read(app, it) }
            changed()
            runCatching { TileService.getUpdater(app).requestUpdate(NowTile::class.java) }
        }
    }

    private fun read(app: Context, item: DataItem) {
        val map = runCatching { DataMapItem.fromDataItem(item).dataMap }.getOrNull() ?: return
        val json = map.getString("json")?.let { runCatching { JSONObject(it) }.getOrNull() } ?: return
        when (item.uri.path) {
            NOW -> {
                now = json
                val asset = map.getAsset("art")
                art = if (asset == null) null else runCatching {
                    val fd = Tasks.await(Wearable.getDataClient(app).getFdForAsset(asset), 10, TimeUnit.SECONDS)
                    fd.inputStream.use { BitmapFactory.decodeStream(it) }
                }.getOrNull()
                app.getSharedPreferences("sound", Context.MODE_PRIVATE).edit().putString("now", json.toString()).apply()
            }
            LISTS -> {
                lists = json
                json.optString("devices").takeIf { it.isNotEmpty() }?.let { Remote.setKey(app, it) }  // hesabın cihaz kanalı
                // listelerin şarkıları (sıkıştırılmış ek): telefon uzaktayken saat bunlardan çalar
                map.getAsset("full")?.let { asset ->
                    runCatching {
                        val fd = Tasks.await(Wearable.getDataClient(app).getFdForAsset(asset), 20, TimeUnit.SECONDS)
                        val text = fd.inputStream.use { java.util.zip.GZIPInputStream(it).bufferedReader().readText() }
                        Lib.save(app, JSONObject(text))
                    }
                }
            }
        }
    }

    /** Kart gibi veri yüklenmeden çağrılan yerler için son bilinen şarkı. */
    fun cached(context: Context): JSONObject? = now ?: context.getSharedPreferences("sound", Context.MODE_PRIVATE)
        .getString("now", null)?.let { runCatching { JSONObject(it) }.getOrNull() }

    /** Telefona komut: toggle, next, previous, like, vol_up, vol_down… */
    fun command(context: Context, action: String) = send(context, "/sound/cmd", action)

    fun play(context: Context, what: JSONObject) = send(context, "/sound/play", what.toString())

    fun send(context: Context, path: String, data: String) {
        val app = context.applicationContext
        io.execute { sendNow(app, path, data) }
    }

    private fun sendNow(app: Context, path: String, data: String): Boolean {
        if (phoneNode == null) findPhone(app)
        val node = phoneNode ?: run { changed(); return false }
        return runCatching {
            Tasks.await(Wearable.getMessageClient(app).sendMessage(node, path, data.toByteArray()), 10, TimeUnit.SECONDS)
        }.onFailure {
            phoneNode = null  // bağlantı koptu: bir dahaki sefere yeniden aranır
            phoneReachable = false
            changed()
        }.isSuccess
    }

    /** Şarkının şu anki konumu (sn): telefonun yazdığı konum + o andan beri geçen süre. */
    fun position(state: JSONObject): Double {
        val pos = state.optDouble("pos", 0.0)
        val dur = state.optDouble("dur", 0.0)
        if (!state.optBoolean("playing")) return pos
        val elapsed = (System.currentTimeMillis() - state.optLong("at")) / 1000.0
        return if (dur > 0) (pos + elapsed).coerceAtMost(dur) else pos + elapsed
    }
}

/** Telefon yeni şarkı / kitaplık yazınca (uygulama kapalıyken de) kart güncellensin. */
class DataService : WearableListenerService() {
    override fun onDataChanged(events: DataEventBuffer) = Link.onData(this, events)
}
