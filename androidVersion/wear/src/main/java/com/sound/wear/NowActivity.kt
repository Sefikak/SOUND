package com.sound.wear

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.drawable.GradientDrawable
import android.media.AudioManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject
import java.util.Locale

/**
 * Saatteki SOUND. Üç çalma yeri (Where): Bluetooth'la bağlı telefondaki SOUND'u kumanda, saatin kendisinde çalma
 * (telefon yokken de; Wi-Fi'dan ya da saate indirilen şarkılardan) ve hesaptaki başka bir SOUND'u (ör. PC) internetten
 * kumanda. Üstteki düğme cihaz seçimini açar. Kapak arka planda, kenarda ilerleme halkası; önceki / çal-duraklat / sonraki,
 * beğen, beğenmedim ve kitaplık. Döner çerçeve (Watch6) ya da dokunmatik çerçeve sesi açıp kısar.
 */
class NowActivity : Activity() {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var art: ImageView
    private lateinit var ring: RingView
    private lateinit var status: TextView
    private lateinit var title: TextView
    private lateinit var artist: TextView
    private lateinit var play: ImageButton
    private lateinit var heart: ImageButton
    private var state: JSONObject? = null  // gösterilen durum: id, title, artist, dur, playing, liked (+ local)
    private var playingGuess: Boolean? = null  // düğmeye basınca hemen değişsin; asıl durum sonra gelir
    private var volume = 0.7
    private var volumeShownUntil = 0L
    private var rotary = 0f
    private val tick = object : Runnable {
        override fun run() {
            drawProgress()
            main.postDelayed(this, 1000)
        }
    }
    private val update = { render() }

    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics)
    private val where get() = Where.get(this)
    private val local get() = where == "watch"
    private val device get() = Where.device(this)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }
        art = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            colorFilter = ColorMatrixColorFilter(ColorMatrix().apply { setScale(0.42f, 0.42f, 0.42f, 1f) })  // karart: yazılar okunsun
        }
        root.addView(art, FrameLayout.LayoutParams(-1, -1))
        root.addView(View(this).apply {
            background = GradientDrawable().apply {
                gradientType = GradientDrawable.RADIAL_GRADIENT
                gradientRadius = dp(260f)
                colors = intArrayOf(0x33000000, 0xCC000000.toInt())
            }
        }, FrameLayout.LayoutParams(-1, -1))
        ring = RingView(this)
        root.addView(ring, FrameLayout.LayoutParams(-1, -1))

        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(26f).toInt(), dp(20f).toInt(), dp(26f).toInt(), dp(16f).toInt())
        }
        status = text(11f, 0xFFB49BFF.toInt(), bold = true).apply {
            letterSpacing = 0.06f
            setPadding(dp(10f).toInt(), dp(3f).toInt(), dp(10f).toInt(), dp(3f).toInt())
            background = GradientDrawable().apply { cornerRadius = dp(12f); setColor(0x33FFFFFF) }
            setOnClickListener {
                performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK)
                startActivity(Intent(this@NowActivity, DevicesActivity::class.java))
            }
        }
        title = text(17f, Color.WHITE, bold = true).apply {
            ellipsize = TextUtils.TruncateAt.MARQUEE
            marqueeRepeatLimit = -1
            isSelected = true
        }
        artist = text(13f, 0xFFC8C8D0.toInt())
        column.addView(status, LinearLayout.LayoutParams(-2, -2))
        column.addView(title, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(4f).toInt() })
        column.addView(artist, LinearLayout.LayoutParams(-1, -2))

        val controls = LinearLayout(this).apply { gravity = Gravity.CENTER; orientation = LinearLayout.HORIZONTAL }
        val prev = icon(R.drawable.ic_prev, 44f) { command("previous") }
        play = icon(R.drawable.ic_play, 60f) { toggle() }.apply {
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xFF8B5CF6.toInt()) }
        }
        val next = icon(R.drawable.ic_next, 44f) { command("next") }
        controls.addView(prev, LinearLayout.LayoutParams(dp(44f).toInt(), dp(44f).toInt()))
        controls.addView(play, LinearLayout.LayoutParams(dp(60f).toInt(), dp(60f).toInt()).apply { marginStart = dp(10f).toInt(); marginEnd = dp(10f).toInt() })
        controls.addView(next, LinearLayout.LayoutParams(dp(44f).toInt(), dp(44f).toInt()))
        column.addView(controls, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(8f).toInt() })

        val extra = LinearLayout(this).apply { gravity = Gravity.CENTER; orientation = LinearLayout.HORIZONTAL }
        val dislike = icon(R.drawable.ic_thumb_down, 34f) { dislike() }
        heart = icon(R.drawable.ic_heart_o, 40f) { like() }
        val library = icon(R.drawable.ic_list, 34f) { startActivity(Intent(this, LibraryActivity::class.java)) }
        extra.addView(dislike, LinearLayout.LayoutParams(dp(36f).toInt(), dp(36f).toInt()))
        extra.addView(heart, LinearLayout.LayoutParams(dp(44f).toInt(), dp(44f).toInt()).apply { marginStart = dp(8f).toInt(); marginEnd = dp(8f).toInt() })
        extra.addView(library, LinearLayout.LayoutParams(dp(36f).toInt(), dp(36f).toInt()))
        column.addView(extra, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(2f).toInt() })

        root.addView(column, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        root.isFocusable = true
        root.isFocusableInTouchMode = true
        root.requestFocus()
        LocalPlayer.init(this)
        Remote.start(this)
        if (local) Py.warm(this)
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)  // çalma ve indirme bildirimleri
        Updater.check(this)
        render()
    }

    private fun toast(text: String, long: Boolean = false) =
        Toast.makeText(this, text, if (long) Toast.LENGTH_LONG else Toast.LENGTH_SHORT).show()

    private fun text(size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        textSize = size
        setTextColor(color)
        gravity = Gravity.CENTER
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
        if (bold) setTypeface(typeface, android.graphics.Typeface.BOLD)
    }

    private fun icon(res: Int, size: Float, onClick: () -> Unit) = ImageButton(this).apply {
        setImageResource(res)
        setBackgroundColor(Color.TRANSPARENT)
        scaleType = ImageView.ScaleType.CENTER_INSIDE
        val pad = (dp(size) * 0.22f).toInt()
        setPadding(pad, pad, pad, pad)
        setOnClickListener { performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK); onClick() }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)  // tek örnek (singleTask): kart ya da bildirimden gelen yeni istek okunabilsin
    }

    override fun onResume() {
        super.onResume()
        Net.acquire(this)  // ekran açıkken internet (Wi-Fi): arama, kapaklar, hesaptaki cihazlar
        Link.listen(update)
        LocalPlayer.listen(update)
        Remote.listen(update)
        Updater.listen(update)
        val debug = applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0
        // debug: telefonun göndereceği kitaplığın yerine dosyadan (adb push → --es libfile <yol>)
        intent.getStringExtra("libfile")?.takeIf { debug }?.let { path ->
            runCatching { Lib.save(this, JSONObject(java.io.File(path).readText())) }
            intent.removeExtra("libfile")
        }
        intent.getStringExtra("devkey")?.takeIf { debug }?.let { Remote.setKey(this, it); intent.removeExtra("devkey") }
        intent.getStringExtra("updurl")?.takeIf { debug }?.let {
            intent.removeExtra("updurl")
            getSharedPreferences("sound", MODE_PRIVATE).edit().putString("update_url", it).apply()
            Updater.check(this, force = true)
        }
        // debug: emülatörde telefon olmadan arayüzü denemek için örnek durum (adb am start --es demo '{...}')
        val demo = intent.getStringExtra("demo")
        if (demo != null && debug) {
            Link.now = JSONObject(demo).put("at", System.currentTimeMillis())
            intent.getStringExtra("lists")?.let { Link.lists = JSONObject(it) }
            Link.phoneReachable = true
        } else Link.start(this)
        render()
        main.post(tick)
    }

    override fun onPause() {
        super.onPause()
        Net.release(this)
        Link.unlisten(update)
        LocalPlayer.unlisten(update)
        Remote.unlisten(update)
        Updater.unlisten(update)
        main.removeCallbacks(tick)
    }

    // ---------- komutlar: çalma yerine göre ----------

    private fun command(name: String) {
        val id = device
        when {
            local -> if (name == "next") LocalPlayer.next(this) else LocalPlayer.previous(this)
            id != null -> Remote.cmd(id, name)
            else -> Link.command(this, name)
        }
    }

    private fun toggle() {
        val id = device
        if (local) {
            if (!LocalPlayer.hasTrack) { startActivity(Intent(this, LibraryActivity::class.java)); return }
            if (!LocalPlayer.playing && !LocalPlayer.headphones(this)) toast("Kulaklık bağlı değil: saatin hoparlöründen çalar")
            LocalPlayer.toggle(this)
            return
        }
        val playing = playingGuess ?: state?.optBoolean("playing") ?: false
        playingGuess = !playing
        play.setImageResource(if (!playing) R.drawable.ic_pause else R.drawable.ic_play)
        if (id != null) { Remote.cmd(id, "toggle"); Remote.guessPlaying(id, !playing) } else Link.command(this, "toggle")
    }

    private fun currentTrack(): JSONObject? {
        val s = state ?: return null
        if (s.optString("id").isEmpty()) return null
        return JSONObject().put("id", s.optString("id")).put("title", s.optString("title")).put("artist", s.optString("artist"))
            .put("duration", s.optDouble("dur", 0.0).toInt())
    }

    private fun like() {
        val track = currentTrack() ?: return
        val liked = !(state?.optBoolean("liked") ?: false)
        state?.put("liked", liked)
        heart.setImageResource(if (liked) R.drawable.ic_heart else R.drawable.ic_heart_o)
        if (where == "phone") Link.command(this, "like") else Lib.setLiked(this, track, liked)  // saat/PC: telefon üzerinden hesaba
        render()
    }

    /** "Beğenmedim": şarkı geçilir, bir daha önerilmez (telefondaki/hesaptaki listeye eklenir). */
    private fun dislike() {
        val track = currentTrack() ?: return
        val id = device
        when {
            where == "phone" -> Link.command(this, "dislike")
            local -> { Lib.dislike(this, track); LocalPlayer.next(this) }
            id != null -> { Lib.dislike(this, track); Remote.cmd(id, "next") }
        }
        toast("Bu şarkı ve benzerleri önerilmeyecek")
    }

    // ---------- görünüm ----------

    private fun accent(): Int = runCatching { Color.parseColor(Link.cached(this)?.optString("accent") ?: "#8b5cf6") }.getOrDefault(0xFF8B5CF6.toInt())

    private fun render() {
        // telefon bulunamadıysa ve telefonda bir şey çalmıyorsa saat kipine geç: telefonsuz da çalabilsin
        if (where == "phone" && Link.phoneReachable == false && Link.now?.optBoolean("playing") != true) Where.set(this, "watch")
        val id = device
        val accent = if (where == "phone") runCatching { Color.parseColor(Link.now?.optString("accent") ?: "#8b5cf6") }.getOrDefault(accent()) else accent()
        (play.background as? GradientDrawable)?.setColor(accent)
        play.setColorFilter(if (luminance(accent) > 0.55) Color.BLACK else Color.WHITE)
        ring.accent = accent
        playingGuess = null
        val volumeShown = System.currentTimeMillis() < volumeShownUntil
        when {
            local -> renderLocal(volumeShown)
            id != null -> renderDevice(id, volumeShown)
            else -> renderPhone(volumeShown)
        }
        val liked = state?.optBoolean("liked") == true
        heart.setImageResource(if (liked) R.drawable.ic_heart else R.drawable.ic_heart_o)
        heart.setColorFilter(if (liked) accent else Color.WHITE)
        drawProgress()
    }

    private fun renderPhone(volumeShown: Boolean) {
        val s = Link.now
        state = s
        val reachable = Link.phoneReachable
        if (s == null || s.optString("id").isEmpty()) {
            title.text = if (reachable == false) "Telefon bulunamadı" else "Şu an bir şey çalmıyor"
            artist.text = if (reachable == false) "Telefonun yakında ve SOUND yüklü olmalı" else "Telefonda SOUND'u aç ya da ▶'a dokun"
            status.text = "📱 TELEFON"
            art.setImageDrawable(null)
        } else {
            title.text = s.optString("title")
            artist.text = s.optString("artist")
            status.text = when {
                volumeShown -> "SES %${(volume * 100).toInt()}"
                reachable == false -> "📱 BAĞLANTI YOK"
                s.optBoolean("playing") -> "📱 TELEFONDA"
                else -> "📱 DURAKLATILDI"
            }
            art.setImageBitmap(Link.art)
            if (!volumeShown) volume = s.optDouble("volume", volume)
        }
        play.setImageResource(if (s?.optBoolean("playing") == true) R.drawable.ic_pause else R.drawable.ic_play)
    }

    private fun renderLocal(volumeShown: Boolean) {
        val s = LocalPlayer.state()
        state = s
        if (s == null) {
            title.text = "Saatte çal"
            artist.text = "Kitaplıktan ya da aramadan seç"
            status.text = "⌚ SAAT"
            art.setImageDrawable(null)
        } else {
            title.text = s.optString("title")
            artist.text = s.optString("artist")
            status.text = when {
                volumeShown -> "SES %${(volume * 100).toInt()}"
                s.optBoolean("loading") -> "⌚ YÜKLENİYOR…"
                s.optString("error").isNotEmpty() && !LocalPlayer.playing -> "⌚ ${s.optString("error").uppercase(Locale.forLanguageTag("tr"))}"
                LocalPlayer.playing -> "⌚ SAATTE"
                else -> "⌚ DURAKLATILDI"
            }
            art.setImageBitmap(LocalPlayer.art)
            if (!volumeShown) volume = streamVolume()
        }
        play.setImageResource(if (LocalPlayer.playing) R.drawable.ic_pause else R.drawable.ic_play)
    }

    /** Hesaptaki başka bir SOUND (ör. PC): Remote'un aldığı durum. */
    private fun renderDevice(id: String, volumeShown: Boolean) {
        val np = Remote.np(id)
        val icon = if (Remote.deviceKind(id) == "phone") "📱" else "💻"
        val name = Remote.deviceName(id).uppercase(Locale.forLanguageTag("tr"))
        val track = np?.optJSONObject("track")
        state = track?.let {
            JSONObject().put("id", it.optString("id")).put("title", it.optString("title")).put("artist", it.optString("artist"))
                .put("dur", it.optDouble("duration", 0.0)).put("playing", np.optBoolean("playing"))
                .put("liked", Lib.isLiked(this, it.optString("id"))).put("remote", id)
        }
        if (track == null) {
            title.text = Remote.deviceName(id)
            artist.text = when {
                !Remote.connected -> "Bağlanıyor…"
                Remote.devices.none { it.optString("id") == id } -> "Cihaz çevrimdışı"
                else -> "Şu an bir şey çalmıyor"
            }
            status.text = "$icon $name"
            art.setImageDrawable(null)
        } else {
            title.text = track.optString("title")
            artist.text = track.optString("artist")
            status.text = if (volumeShown) "SES %${(volume * 100).toInt()}" else "$icon $name"
            art.setImageBitmap(Remote.artFor(track.optString("id")))
            if (!volumeShown) volume = np.optDouble("volume", volume)
        }
        play.setImageResource(if (np?.optBoolean("playing") == true) R.drawable.ic_pause else R.drawable.ic_play)
    }

    private fun audio() = getSystemService(AudioManager::class.java)

    private fun streamVolume(): Double {
        val am = audio()
        val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC).coerceAtLeast(1)
        return am.getStreamVolume(AudioManager.STREAM_MUSIC).toDouble() / max
    }

    private fun luminance(c: Int) = (0.2126 * Color.red(c) + 0.7152 * Color.green(c) + 0.0722 * Color.blue(c)) / 255

    private fun drawProgress() {
        val s = state
        if (System.currentTimeMillis() < volumeShownUntil) {
            ring.set(volume.toFloat(), volumeMode = true)
            return
        }
        if (status.text.startsWith("SES")) render()
        val dur = s?.optDouble("dur", 0.0) ?: 0.0
        val id = device
        val pos = when {
            s == null -> 0.0
            s.optBoolean("local") -> LocalPlayer.position()
            id != null -> Remote.np(id)?.let { Remote.position(it) } ?: 0.0
            else -> Link.position(s)
        }
        ring.set(if (s != null && dur > 0) (pos / dur).toFloat() else 0f, volumeMode = false)
    }

    /** Döner çerçeve: bir çentik ≈ %5 ses (saatte çalarken saatin sesi, değilse çalan cihazın). */
    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_SCROLL && event.isFromSource(InputDevice.SOURCE_ROTARY_ENCODER)) {
            rotary += -event.getAxisValue(MotionEvent.AXIS_SCROLL)
            val id = device
            while (rotary >= 1f || rotary <= -1f) {
                val up = rotary > 0  // saat yönünde (AXIS_SCROLL eksi): aç
                rotary -= if (up) 1f else -1f
                when {
                    local -> {
                        audio().adjustStreamVolume(AudioManager.STREAM_MUSIC, if (up) AudioManager.ADJUST_RAISE else AudioManager.ADJUST_LOWER, 0)
                        volume = streamVolume()
                    }
                    id != null -> {
                        volume = (volume + if (up) 0.05 else -0.05).coerceIn(0.0, 1.0)
                        Remote.setVolume(id, volume)
                    }
                    else -> {
                        volume = (volume + if (up) 0.05 else -0.05).coerceIn(0.0, 1.0)
                        Link.command(this, if (up) "vol_up" else "vol_down")
                    }
                }
            }
            volumeShownUntil = System.currentTimeMillis() + 1500
            status.text = "SES %${(volume * 100).toInt()}"
            ring.set(volume.toFloat(), volumeMode = true)
            return true
        }
        return super.onGenericMotionEvent(event)
    }
}

/** Ekranın kenarındaki halka: şarkının ilerlemesi (vurgu renginde) ya da döner çerçeve çevrilirken ses (beyaz). */
class RingView(context: Context) : View(context) {
    var accent = 0xFF8B5CF6.toInt()
    private var value = 0f
    private var volumeMode = false
    private val stroke = 5f * resources.displayMetrics.density
    private val track = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = stroke; color = 0x33FFFFFF }
    private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = stroke; strokeCap = Paint.Cap.ROUND }
    private val box = RectF()

    fun set(v: Float, volumeMode: Boolean) {
        val clamped = v.coerceIn(0f, 1f)
        if (clamped == value && volumeMode == this.volumeMode) return
        value = clamped
        this.volumeMode = volumeMode
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val inset = stroke / 2 + 3 * resources.displayMetrics.density
        box.set(inset, inset, width - inset, height - inset)
        canvas.drawArc(box, 0f, 360f, false, track)
        fill.color = if (volumeMode) Color.WHITE else accent
        if (value > 0f) canvas.drawArc(box, -90f, 360f * value, false, fill)
    }
}
