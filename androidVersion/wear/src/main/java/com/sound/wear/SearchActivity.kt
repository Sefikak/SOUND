package com.sound.wear

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.speech.RecognizerIntent
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.InputDevice
import android.view.MotionEvent
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject

/** Saatte arama (klavye ya da ses). Seçilen şarkı çalma yerine göre saatte ya da telefonda çalar, ardından benzerleri gelir. */
class SearchActivity : Activity() {
    private lateinit var scroll: ScrollView
    private lateinit var list: LinearLayout
    private lateinit var results: LinearLayout
    private lateinit var input: EditText
    private var searching = 0

    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Py.warm(this)
        list = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(22f), dp(28f), dp(22f), dp(46f))
        }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12f), 0, dp(4f), 0)
            background = GradientDrawable().apply { cornerRadius = dp(22f).toFloat(); setColor(0xFF26262C.toInt()) }
        }
        input = EditText(this).apply {
            hint = "Ara"
            setHintTextColor(0xFF9A9AA4.toInt())
            setTextColor(Color.WHITE)
            textSize = 14f
            isSingleLine = true
            background = null
            imeOptions = EditorInfo.IME_ACTION_SEARCH
            setOnEditorActionListener { _, action, _ -> if (action == EditorInfo.IME_ACTION_SEARCH || action == EditorInfo.IME_ACTION_DONE) { search(text.toString()); true } else false }
        }
        bar.addView(input, LinearLayout.LayoutParams(0, dp(44f), 1f))
        bar.addView(ImageButton(this).apply {
            setImageResource(R.drawable.ic_mic)
            setBackgroundColor(Color.TRANSPARENT)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            contentDescription = "Sesle ara"
            setOnClickListener { voice() }
        }, LinearLayout.LayoutParams(dp(40f), dp(40f)))
        list.addView(bar, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8f) })
        results = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        list.addView(results)
        scroll = ScrollView(this).apply { setBackgroundColor(Color.BLACK); addView(list) }
        setContentView(scroll)
        input.requestFocus()
    }

    override fun onResume() {
        super.onResume()
        Net.acquire(this)
    }

    override fun onPause() {
        super.onPause()
        Net.release(this)
    }

    private fun voice() {
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_PROMPT, "Şarkı ya da sanatçı söyle")
        try {
            @Suppress("DEPRECATION") startActivityForResult(intent, 1)
        } catch (_: ActivityNotFoundException) {
            input.requestFocus()
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val text = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()
        if (requestCode == 1 && resultCode == RESULT_OK && !text.isNullOrBlank()) {
            input.setText(text)
            search(text)
        }
    }

    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_SCROLL && event.isFromSource(InputDevice.SOURCE_ROTARY_ENCODER)) {
            scroll.smoothScrollBy(0, (-event.getAxisValue(MotionEvent.AXIS_SCROLL) * dp(48f)).toInt())
            return true
        }
        return super.onGenericMotionEvent(event)
    }

    private fun search(query: String) {
        if (query.isBlank()) return
        val my = ++searching
        results.removeAllViews()
        results.addView(note("Aranıyor…"))
        Py.async(this, "search", query.trim()) { result ->
            if (my != searching || isFinishing) return@async
            results.removeAllViews()
            val tracks = result.optJSONArray("tracks")
            if (tracks == null) {
                results.addView(note(if (result.optBoolean("network")) "İnternet yok. Saati Wi-Fi'a bağla." else result.optString("error", "Aranamadı")))
                return@async
            }
            if (tracks.length() == 0) results.addView(note("Sonuç yok"))
            for (i in 0 until tracks.length()) row(tracks.getJSONObject(i))
        }
    }

    private fun note(s: String) = TextView(this).apply {
        text = s; textSize = 13f; setTextColor(0xFFB0B0B8.toInt()); gravity = Gravity.CENTER
        setPadding(0, dp(10f), 0, 0)
    }

    private fun row(t: JSONObject) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14f), dp(9f), dp(14f), dp(9f))
            background = GradientDrawable().apply { cornerRadius = dp(24f).toFloat(); setColor(0xFF1E1E22.toInt()) }
            isClickable = true
            setOnClickListener { play(t) }
        }
        box.addView(TextView(this).apply {
            text = t.optString("title"); textSize = 14f; setTextColor(Color.WHITE); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
            setTypeface(typeface, Typeface.BOLD)
        })
        box.addView(TextView(this).apply {
            text = t.optString("artist"); textSize = 11.5f; setTextColor(0xFFB8B8C0.toInt()); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
        })
        results.addView(box, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(5f) })
    }

    private fun play(t: JSONObject) {
        val device = Where.device(this)
        if (Where.watch(this)) {
            if (!LocalPlayer.headphones(this)) Toast.makeText(this, "Kulaklık bağlı değil: saatin hoparlöründen çalar", Toast.LENGTH_SHORT).show()
            LocalPlayer.playList(this, JSONArray().put(t))
        } else if (device != null) {
            Remote.cmd(device, "playlist") { put("tracks", JSONArray().put(Lib.slim(t))).put("index", 0) }
            Toast.makeText(this, "${Remote.deviceName(device)} çalıyor", Toast.LENGTH_SHORT).show()
        } else {
            Link.play(this, JSONObject().put("kind", "track").put("id", t.optString("id")).put("track", Lib.slim(t)))
            Toast.makeText(this, "Telefonda çalıyor", Toast.LENGTH_SHORT).show()
        }
        startActivity(Intent(this, NowActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT))
        finish()
    }
}
