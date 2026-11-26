package com.sound.wear

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.InputDevice
import android.view.MotionEvent
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject

/**
 * Saatte kitaplık: Ara, saate indirilenler, Favoriler, mixler, albümler ve son çalınanlar. Seçilen liste çalma yerine göre
 * telefonda ya da saatte çalar. Listelerin yanındaki düğme listeyi saate indirir (internetsiz dinlemek için).
 */
class LibraryActivity : Activity() {
    private lateinit var scroll: ScrollView
    private lateinit var list: LinearLayout
    private val update = { render() }
    private var confirmRemove: String? = null
    private var confirmUntil = 0L

    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics).toInt()
    private val local get() = Where.watch(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22f), dp(30f), dp(22f), dp(46f))
        }
        scroll = ScrollView(this).apply {
            setBackgroundColor(Color.BLACK)
            isVerticalScrollBarEnabled = true
            addView(list)
        }
        setContentView(scroll)
        render()
        scroll.post { scroll.requestFocus() }
        if (local) Py.warm(this)
    }

    override fun onResume() {
        super.onResume()
        Net.acquire(this)  // ekran açıkken internet (Wi-Fi): arama, kapaklar, hesaptaki cihazlar
        Link.listen(update)
        Offline.listen(update)
        Updater.listen(update)
        Link.start(this)
        render()
    }

    override fun onPause() {
        super.onPause()
        Net.release(this)
        Link.unlisten(update)
        Offline.unlisten(update)
        Updater.unlisten(update)
    }

    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_SCROLL && event.isFromSource(InputDevice.SOURCE_ROTARY_ENCODER)) {
            scroll.smoothScrollBy(0, (-event.getAxisValue(MotionEvent.AXIS_SCROLL) * dp(48f)).toInt())
            return true
        }
        return super.onGenericMotionEvent(event)
    }

    private fun render() {
        list.removeAllViews()
        list.addView(TextView(this).apply {
            text = "Kitaplık"
            textSize = 16f
            setTextColor(Color.WHITE)
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2))
        val device = Where.device(this)
        list.addView(note(when {
            local -> "⌚ Saatte çalar"
            device != null -> "💻 ${Remote.deviceName(device)} çalar"
            else -> "📱 Telefonda çalar"
        }).apply { textSize = 11.5f },
            LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8f) })
        val accent = runCatching { Color.parseColor(Link.cached(this)?.optString("accent") ?: "#8b5cf6") }.getOrDefault(0xFF8B5CF6.toInt())

        Updater.ready?.let { version ->
            row("Güncelleme hazır", "SOUND $version · yüklemek için dokun", 0xFF1F3A2E.toInt(), R.drawable.ic_download) { Updater.install(this) }
        }
        row("Ara", "Şarkı ya da sanatçı", 0xFF26262C.toInt(), R.drawable.ic_search) { startActivity(Intent(this, SearchActivity::class.java)) }

        // saate indirilenler
        var showListsHeader = false
        val offline = Offline.all(this)
        if (offline.length() > 0) {
            header("Saatte")
            showListsHeader = true
            val all = Offline.allTracks(this)
            if (all.length() > 0) row("Tüm indirilenler", "${all.length()} şarkı · karışık", 0xFF1F3A2E.toInt(), R.drawable.ic_download) {
                playHere(shuffled(all))
            }
        }

        val lib = Lib.get(this)
        val summary = Link.lists
        if (lib == null && summary == null) {
            list.addView(note(if (Link.phoneReachable == false) "Telefondan liste gelmedi. SOUND telefonda açıkken saat listeleri alır; o zamana kadar arayabilirsin."
                else "Telefondan liste bekleniyor…"))
            return
        }
        val favCount = lib?.optJSONArray("favorites")?.length() ?: summary?.optInt("favorites") ?: 0
        if (favCount > 0) {
            if (showListsHeader) header("Kitaplık")
            listRow("favorites", "Favoriler", "$favCount şarkı", accent, JSONObject().put("kind", "favorites")) { Lib.tracks(this, "favorites") }
        }
        val mixes = lib?.optJSONArray("mixes") ?: summary?.optJSONArray("mixes")
        if (mixes != null && mixes.length() > 0) {
            header("Senin için mixler")
            for (i in 0 until mixes.length()) {
                val m = mixes.getJSONObject(i)
                val key = m.optString("key")
                listRow("mix:$key", m.optString("title"), m.optString("sub"), 0xFF2A2140.toInt(), JSONObject().put("kind", "mix").put("key", key)) {
                    Lib.tracks(this, "mix", key)
                }
            }
        }
        val albums = lib?.optJSONArray("albums") ?: summary?.optJSONArray("albums")
        if (albums != null && albums.length() > 0) {
            header("Albümler")
            for (i in 0 until albums.length()) {
                val a = albums.getJSONObject(i)
                val id = a.optString("id")
                val count = a.optJSONArray("tracks")?.length() ?: a.optInt("count")
                listRow("album:$id", a.optString("title"), "$count şarkı", 0xFF1E1E22.toInt(), JSONObject().put("kind", "album").put("id", id)) {
                    Lib.tracks(this, "album", id)
                }
            }
        }
        val recent = lib?.optJSONArray("recent") ?: summary?.optJSONArray("recent")
        if (recent != null && recent.length() > 0) {
            header("Son çalınanlar")
            for (i in 0 until recent.length()) {
                val t = recent.getJSONObject(i)
                row(t.optString("title"), t.optString("artist"), 0xFF1E1E22.toInt(), null) {
                    when {
                        local -> playHere(JSONArray().put(t))
                        Where.device(this) != null -> sendToDevice(JSONArray().put(Lib.slim(t)))
                        else -> sendToPhone(JSONObject().put("kind", "track").put("id", t.optString("id")).put("track", Lib.slim(t)))
                    }
                }
            }
        }
    }

    private fun shuffled(tracks: JSONArray): JSONArray {
        val items = (0 until tracks.length()).map { tracks.getJSONObject(it) }.shuffled()
        return JSONArray(items)
    }

    private fun playHere(tracks: JSONArray) {
        if (tracks.length() == 0) {
            Toast.makeText(this, "Bu listenin şarkıları saatte yok. Telefon yakındayken SOUND'u aç.", Toast.LENGTH_LONG).show()
            return
        }
        if (!LocalPlayer.headphones(this)) Toast.makeText(this, "Kulaklık bağlı değil: saatin hoparlöründen çalar", Toast.LENGTH_SHORT).show()
        LocalPlayer.playList(this, tracks)
        startActivity(Intent(this, NowActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
        finish()
    }

    /** Hesaptaki cihazda (ör. PC) çal: liste olduğu gibi gider. */
    private fun sendToDevice(tracks: JSONArray) {
        val id = Where.device(this) ?: return
        if (tracks.length() == 0) {
            Toast.makeText(this, "Bu listenin şarkıları saatte yok. Telefon yakındayken SOUND'u aç.", Toast.LENGTH_LONG).show()
            return
        }
        val out = JSONArray()
        for (i in 0 until minOf(100, tracks.length())) out.put(Lib.slim(tracks.getJSONObject(i)))
        Remote.cmd(id, "playlist") { put("tracks", out).put("index", 0) }
        Toast.makeText(this, "${Remote.deviceName(id)} çalıyor", Toast.LENGTH_SHORT).show()
        startActivity(Intent(this, NowActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
        finish()
    }

    private fun sendToPhone(what: JSONObject) {
        Link.play(this, what)
        Toast.makeText(this, "Telefonda çalıyor", Toast.LENGTH_SHORT).show()
        finish()
    }

    private fun note(s: String) = TextView(this).apply {
        text = s
        textSize = 13f
        setTextColor(0xFFB0B0B8.toInt())
        gravity = Gravity.CENTER
    }

    private fun header(s: String) {
        list.addView(TextView(this).apply {
            text = s.uppercase(java.util.Locale.forLanguageTag("tr"))
            textSize = 11f
            letterSpacing = 0.06f
            setTextColor(0xFFB49BFF.toInt())
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12f); bottomMargin = dp(4f) })
    }

    /** Bir liste satırı: dokununca çalar (saatte ya da telefonda); sağdaki düğme saate indirir / indirileni siler. */
    private fun listRow(key: String, title: String, sub: String, color: Int, phoneWhat: JSONObject, tracks: () -> JSONArray) {
        val box = row(title, sub, color, null) {
            val t = tracks()
            when {
                local -> playHere(if (key == "favorites") shuffled(t) else t)
                Where.device(this) != null -> sendToDevice(if (key == "favorites") shuffled(t) else t)
                else -> sendToPhone(phoneWhat)
            }
        }
        if (Lib.get(this) == null) return  // şarkılar saatte yok: indirilemez
        val progress = Offline.progress[key]
        val saved = Offline.has(this, key)
        val button = ImageButton(this).apply {
            setBackgroundColor(Color.TRANSPARENT)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            setPadding(dp(5f), dp(5f), dp(5f), dp(5f))
            setImageResource(if (saved && progress == null) R.drawable.ic_check else R.drawable.ic_download)
            setColorFilter(if (saved) 0xFF7CE0A6.toInt() else 0xFFB8B8C0.toInt())
            alpha = if (progress != null) 0.5f else 1f
            contentDescription = if (saved) "Saatten sil" else "Saate indir"
            setOnClickListener {
                if (!saved) {
                    val t = tracks()
                    if (t.length() == 0) return@setOnClickListener
                    Offline.add(this@LibraryActivity, key, title, t)
                    Toast.makeText(this@LibraryActivity, "Saate indiriliyor (${t.length()} şarkı)", Toast.LENGTH_SHORT).show()
                } else if (confirmRemove == key && System.currentTimeMillis() < confirmUntil) {
                    Offline.remove(this@LibraryActivity, key)
                    Toast.makeText(this@LibraryActivity, "Saatten silindi", Toast.LENGTH_SHORT).show()
                } else {
                    confirmRemove = key
                    confirmUntil = System.currentTimeMillis() + 3000
                    Toast.makeText(this@LibraryActivity, "Saatten silmek için yeniden dokun", Toast.LENGTH_SHORT).show()
                }
            }
        }
        box.addView(button, LinearLayout.LayoutParams(dp(30f), dp(30f)))
        if (progress != null) (box.getChildAt(0) as? LinearLayout)?.getChildAt(1)?.let { (it as? TextView)?.text = "İndiriliyor ${progress.first}/${progress.second}" }
    }

    private fun row(title: String, sub: String, color: Int, iconRes: Int?, onClick: () -> Unit): LinearLayout {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14f), dp(9f), dp(8f), dp(9f))
            background = GradientDrawable().apply { cornerRadius = dp(24f).toFloat(); setColor(color) }
            isClickable = true
            setOnClickListener { performHapticFeedback(android.view.HapticFeedbackConstants.CONTEXT_CLICK); onClick() }
        }
        val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        texts.addView(TextView(this).apply {
            text = title; textSize = 14f; setTextColor(Color.WHITE); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
            setTypeface(typeface, Typeface.BOLD)
        })
        texts.addView(TextView(this).apply {
            text = sub; textSize = 11.5f; setTextColor(0xFFB8B8C0.toInt()); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
            visibility = if (sub.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE
        })
        if (iconRes != null) box.addView(ImageView(this).apply { setImageResource(iconRes); setColorFilter(0xFFDDDDE4.toInt()) },
            LinearLayout.LayoutParams(dp(20f), dp(20f)).apply { marginEnd = dp(10f) })
        box.addView(texts, LinearLayout.LayoutParams(0, -2, 1f))
        list.addView(box, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(5f) })
        return box
    }
}
