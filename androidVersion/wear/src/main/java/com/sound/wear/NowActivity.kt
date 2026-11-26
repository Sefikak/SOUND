package com.sound.wear

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject

/**
 * Saatteki SOUND: telefonda çalan şarkı. Kapak arka planda, kenarda ilerleme halkası; önceki / çal-duraklat / sonraki,
 * beğen ve kitaplık. Döner çerçeve (Watch6) ya da dokunmatik çerçeve sesi açıp kısar.
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
    private var state: JSONObject? = null
    private var playingLocal: Boolean? = null  // düğmeye basınca hemen değişsin; telefondan gelen asıl durum sonra
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
            setPadding(dp(26f).toInt(), dp(20f).toInt(), dp(26f).toInt(), dp(18f).toInt())
        }
        status = text(11f, 0xFFB49BFF.toInt(), bold = true).apply { letterSpacing = 0.06f }
        title = text(17f, Color.WHITE, bold = true).apply {
            ellipsize = TextUtils.TruncateAt.MARQUEE
            marqueeRepeatLimit = -1
            isSelected = true
        }
        artist = text(13f, 0xFFC8C8D0.toInt())
        column.addView(status)
        column.addView(title, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(4f).toInt() })
        column.addView(artist, LinearLayout.LayoutParams(-1, -2))

        val controls = LinearLayout(this).apply { gravity = Gravity.CENTER; orientation = LinearLayout.HORIZONTAL }
        val prev = icon(R.drawable.ic_prev, 44f) { Link.command(this, "previous") }
        play = icon(R.drawable.ic_play, 60f) { toggle() }.apply {
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(0xFF8B5CF6.toInt()) }
        }
        val next = icon(R.drawable.ic_next, 44f) { Link.command(this, "next") }
        controls.addView(prev, LinearLayout.LayoutParams(dp(44f).toInt(), dp(44f).toInt()))
        controls.addView(play, LinearLayout.LayoutParams(dp(60f).toInt(), dp(60f).toInt()).apply { marginStart = dp(10f).toInt(); marginEnd = dp(10f).toInt() })
        controls.addView(next, LinearLayout.LayoutParams(dp(44f).toInt(), dp(44f).toInt()))
        column.addView(controls, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(10f).toInt() })

        val extra = LinearLayout(this).apply { gravity = Gravity.CENTER; orientation = LinearLayout.HORIZONTAL }
        heart = icon(R.drawable.ic_heart_o, 36f) { like() }
        val library = icon(R.drawable.ic_list, 36f) { startActivity(Intent(this, LibraryActivity::class.java)) }
        extra.addView(heart, LinearLayout.LayoutParams(dp(40f).toInt(), dp(40f).toInt()).apply { marginEnd = dp(18f).toInt() })
        extra.addView(library, LinearLayout.LayoutParams(dp(40f).toInt(), dp(40f).toInt()))
        column.addView(extra, LinearLayout.LayoutParams(-2, -2).apply { topMargin = dp(4f).toInt() })

        root.addView(column, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        root.isFocusable = true
        root.isFocusableInTouchMode = true
        root.requestFocus()
        render()
    }

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
        setOnClickListener { performHapticFeedback(android.view.HapticFeedbackConstants.CONTEXT_CLICK); onClick() }
    }

    override fun onResume() {
        super.onResume()
        Link.listen(update)
        // yalnızca debug derlemede: emülatörde telefon olmadan arayüzü denemek için örnek durum (adb am start --es demo '{...}')
        val demo = intent.getStringExtra("demo")
        if (demo != null && applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE != 0) {
            Link.now = JSONObject(demo).put("at", System.currentTimeMillis())
            intent.getStringExtra("lists")?.let { Link.lists = JSONObject(it) }
            Link.phoneReachable = true
            render()
        } else Link.start(this)
        main.post(tick)
    }

    override fun onPause() {
        super.onPause()
        Link.unlisten(update)
        main.removeCallbacks(tick)
    }

    private fun toggle() {
        val playing = playingLocal ?: state?.optBoolean("playing") ?: false
        playingLocal = !playing
        play.setImageResource(if (!playing) R.drawable.ic_pause else R.drawable.ic_play)
        Link.command(this, "toggle")
    }

    private fun like() {
        val s = state ?: return
        val liked = !s.optBoolean("liked")
        s.put("liked", liked)
        heart.setImageResource(if (liked) R.drawable.ic_heart else R.drawable.ic_heart_o)
        Link.command(this, "like")
    }

    private fun render() {
        val s = Link.now
        state = s
        playingLocal = null
        val reachable = Link.phoneReachable
        val accent = runCatching { Color.parseColor(s?.optString("accent") ?: "#8b5cf6") }.getOrDefault(0xFF8B5CF6.toInt())
        (play.background as? GradientDrawable)?.setColor(accent)
        play.setColorFilter(if (luminance(accent) > 0.55) Color.BLACK else Color.WHITE)
        ring.accent = accent
        if (s == null || s.optString("id").isEmpty()) {
            title.text = if (reachable == false) "Telefon bulunamadı" else "Şu an bir şey çalmıyor"
            artist.text = if (reachable == false) "Telefonun yakında ve SOUND yüklü olmalı" else "Telefonda SOUND'u aç ya da ▶'a dokun"
            status.text = "SOUND"
            art.setImageDrawable(null)
        } else {
            title.text = s.optString("title")
            artist.text = s.optString("artist")
            status.text = when {
                System.currentTimeMillis() < volumeShownUntil -> "SES %${(volume * 100).toInt()}"
                reachable == false -> "BAĞLANTI YOK"
                s.optBoolean("playing") -> "TELEFONDA ÇALIYOR"
                else -> "DURAKLATILDI"
            }
            art.setImageBitmap(Link.art)
            if (System.currentTimeMillis() >= volumeShownUntil) volume = s.optDouble("volume", volume)
        }
        play.setImageResource(if (s?.optBoolean("playing") == true) R.drawable.ic_pause else R.drawable.ic_play)
        heart.setImageResource(if (s?.optBoolean("liked") == true) R.drawable.ic_heart else R.drawable.ic_heart_o)
        heart.setColorFilter(if (s?.optBoolean("liked") == true) accent else Color.WHITE)
        drawProgress()
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
        ring.set(if (s != null && dur > 0) (Link.position(s) / dur).toFloat() else 0f, volumeMode = false)
    }

    /** Döner çerçeve: bir çentik ≈ %5 ses. Telefondaki SOUND'un sesi değişir. */
    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_SCROLL && event.isFromSource(InputDevice.SOURCE_ROTARY_ENCODER)) {
            rotary += -event.getAxisValue(MotionEvent.AXIS_SCROLL)
            while (rotary >= 1f || rotary <= -1f) {
                val up = rotary > 0  // saat yönünde (AXIS_SCROLL eksi): aç
                rotary -= if (up) 1f else -1f
                volume = (volume + if (up) 0.05 else -0.05).coerceIn(0.0, 1.0)
                Link.command(this, if (up) "vol_up" else "vol_down")
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
