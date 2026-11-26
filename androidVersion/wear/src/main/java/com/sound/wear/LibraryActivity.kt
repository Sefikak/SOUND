package com.sound.wear

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.InputDevice
import android.view.MotionEvent
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject

/** Saatte kitaplık: Favoriler, mixler, albümler ve son çalınanlar. Dokununca telefonda çalar. Döner çerçeveyle kayar. */
class LibraryActivity : Activity() {
    private lateinit var scroll: ScrollView
    private lateinit var list: LinearLayout
    private val update = { render() }

    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics).toInt()

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
    }

    override fun onResume() {
        super.onResume()
        Link.listen(update)
        Link.start(this)
    }

    override fun onPause() {
        super.onPause()
        Link.unlisten(update)
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
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8f) })
        val data = Link.lists
        if (data == null) {
            list.addView(note(if (Link.phoneReachable == false) "Telefon bulunamadı. SOUND telefonda açık olmalı." else "Telefondan liste bekleniyor…"))
            return
        }
        val accent = runCatching { Color.parseColor(Link.now?.optString("accent") ?: "#8b5cf6") }.getOrDefault(0xFF8B5CF6.toInt())
        if (data.optInt("favorites") > 0) {
            row("Favoriler", "${data.optInt("favorites")} şarkı", accent) { JSONObject().put("kind", "favorites") }
        }
        val mixes = data.optJSONArray("mixes")
        if (mixes != null && mixes.length() > 0) {
            header("Senin için mixler")
            for (i in 0 until mixes.length()) {
                val m = mixes.getJSONObject(i)
                row(m.optString("title"), m.optString("sub"), 0xFF2A2140.toInt()) { JSONObject().put("kind", "mix").put("key", m.optString("key")) }
            }
        }
        val albums = data.optJSONArray("albums")
        if (albums != null && albums.length() > 0) {
            header("Albümler")
            for (i in 0 until albums.length()) {
                val a = albums.getJSONObject(i)
                row(a.optString("title"), "${a.optInt("count")} şarkı", 0xFF1E1E22.toInt()) { JSONObject().put("kind", "album").put("id", a.optString("id")) }
            }
        }
        val recent = data.optJSONArray("recent")
        if (recent != null && recent.length() > 0) {
            header("Son çalınanlar")
            for (i in 0 until recent.length()) {
                val t = recent.getJSONObject(i)
                row(t.optString("title"), t.optString("artist"), 0xFF1E1E22.toInt()) { JSONObject().put("kind", "track").put("id", t.optString("id")) }
            }
        }
    }

    private fun note(s: String) = TextView(this).apply {
        text = s
        textSize = 13f
        setTextColor(0xFFB0B0B8.toInt())
        gravity = Gravity.CENTER
    }

    private fun header(s: String) {
        list.addView(TextView(this).apply {
            text = s.uppercase(java.util.Locale("tr"))
            textSize = 11f
            letterSpacing = 0.06f
            setTextColor(0xFFB49BFF.toInt())
            setTypeface(typeface, Typeface.BOLD)
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12f); bottomMargin = dp(4f) })
    }

    private fun row(title: String, sub: String, color: Int, what: () -> JSONObject) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14f), dp(9f), dp(14f), dp(9f))
            background = GradientDrawable().apply { cornerRadius = dp(24f).toFloat(); setColor(color) }
            isClickable = true
            setOnClickListener {
                Link.play(this@LibraryActivity, what())
                Toast.makeText(this@LibraryActivity, "Telefonda çalıyor", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
        box.addView(TextView(this).apply {
            text = title; textSize = 14f; setTextColor(Color.WHITE); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
            setTypeface(typeface, Typeface.BOLD)
        })
        if (sub.isNotEmpty()) box.addView(TextView(this).apply {
            text = sub; textSize = 11.5f; setTextColor(0xFFB8B8C0.toInt()); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
        })
        list.addView(box, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(5f) })
    }
}
