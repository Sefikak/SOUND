package com.sound.app

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import com.chaquo.python.Python
import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.Asset
import com.google.android.gms.wearable.MessageEvent
import com.google.android.gms.wearable.PutDataMapRequest
import com.google.android.gms.wearable.Wearable
import com.google.android.gms.wearable.WearableListenerService
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Galaxy Watch (Wear OS) uygulamasıyla bağlantı. Telefon çalan şarkıyı, kapağı ve kitaplık listelerini Data Layer'a yazar
 * (/sound/now, /sound/lists); saatin komutları WatchService'e mesaj olarak gelir. Saat yoksa yazılan veri yalnızca
 * telefonda bekler, maliyeti yoktur. Play Hizmetleri olmayan telefonlarda sessizce devre dışı kalır.
 */
object WatchLink {
    const val NOW = "/sound/now"
    const val LISTS = "/sound/lists"
    private val io = Executors.newSingleThreadExecutor()
    private var state = JSONObject()
    private var art: ByteArray? = null
    private var artId: String? = null
    private var listsJson: String? = null

    /** Arayüzdeki çalma durumu (android_main.player_state: şarkı, çalıyor mu, beğeni, ses, vurgu rengi). */
    fun publishState(context: Context, json: JSONObject) {
        val track = json.optJSONObject("track")
        val now = JSONObject()
            .put("id", track?.optString("id") ?: "")
            .put("title", track?.optString("title") ?: "")
            .put("artist", track?.optString("artist") ?: "")
            .put("dur", track?.optDouble("duration", 0.0) ?: 0.0)
            .put("pos", json.optDouble("position", 0.0))
            .put("playing", json.optBoolean("playing") || json.optBoolean("loading"))
            .put("liked", json.optBoolean("liked"))
            .put("volume", json.optDouble("volume", 0.7))
            .put("shuffle", json.optBoolean("shuffle"))
            .put("repeat", json.optString("repeat", "off"))
            .put("accent", json.optString("accent", "#8b5cf6"))
            .put("at", System.currentTimeMillis())
        state = now
        put(context, NOW, now.toString(), if (artId == now.optString("id")) art else null)
    }

    /** Kapak (bildirim için zaten indirilen): saate küçük JPEG olarak gider. */
    fun publishArt(context: Context, id: String, bitmap: Bitmap) {
        val size = 240
        val scaled = runCatching { Bitmap.createScaledBitmap(bitmap, size, size * bitmap.height / maxOf(1, bitmap.width), true) }.getOrNull() ?: return
        art = ByteArrayOutputStream().use { out -> scaled.compress(Bitmap.CompressFormat.JPEG, 80, out); out.toByteArray() }
        artId = id
        if (state.optString("id") == id) put(context, NOW, state.put("at", System.currentTimeMillis()).toString(), art)
    }

    /** Saatteki Kitaplık ekranı: favoriler, mixler, albümler (android_main.watch_lists). */
    fun publishLists(context: Context, json: String) {
        if (json == listsJson) return
        listsJson = json
        put(context, LISTS, json, null)
    }

    private fun put(context: Context, path: String, json: String, image: ByteArray?) {
        val app = context.applicationContext
        io.execute {
            runCatching {
                val request = PutDataMapRequest.create(path)
                request.dataMap.putString("json", json)
                image?.let { request.dataMap.putAsset("art", Asset.createFromBytes(it)) }
                Tasks.await(Wearable.getDataClient(app).putDataItem(request.asPutDataRequest().setUrgent()), 10, TimeUnit.SECONDS)
            }.onFailure { Log.d("SOUND", "Saate yazılamadı ($path): ${it.message}") }
        }
    }

    /** Saat bağlandı / uygulama açıldı: son durum yeniden yazılır (Data Layer zaten saklar; yine de taze zaman damgası). */
    fun refresh(context: Context) {
        if (state.length() > 0) put(context, NOW, state.put("at", System.currentTimeMillis()).toString(), if (artId == state.optString("id")) art else null)
        listsJson?.let { put(context, LISTS, it, null) }
    }
}

/** Saatten gelen komutlar: /sound/cmd (toggle, next, previous, like, vol_up, vol_down…), /sound/play (bir liste), /sound/hello. */
class WatchService : WearableListenerService() {
    override fun onMessageReceived(event: MessageEvent) {
        val data = String(event.data)
        val ready = Engine.running && Engine.loaded
        when (event.path) {
            "/sound/cmd" -> {
                if (ready) call("command", data)
                else if (data == "toggle" || data == "play") PlaybackService.command(this, "play")  // SOUND kapalı: ekransız başlat
            }
            "/sound/play" -> {
                if (ready) call("watch_play", data) else PlaybackService.command(this, "play")
            }
            "/sound/hello" -> {
                WatchLink.refresh(this)
                if (ready) call("watch_lists_now")
            }
        }
    }

    private fun call(name: String, vararg args: String) {
        Engine.pool.execute {
            runCatching { Python.getInstance().getModule("android_main").callAttr(name, *args) }
                .onFailure { Log.w("SOUND", "Saat komutu iletilemedi: $name", it) }
        }
    }
}
