package com.sound.wear

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.TextUtils
import android.util.TypedValue
import android.view.Gravity
import android.view.HapticFeedbackConstants
import android.view.InputDevice
import android.view.MotionEvent
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject

/**
 * Nerede çalsın / neyi kumanda edeyim: bu saat, Bluetooth'la bağlı telefon ve hesaptaki diğer SOUND'lar (PC, telefon).
 * Seçilen yerde bir şey çalıyorsa ekran onu gösterir; şu an başka yerde çalan şarkı da seçilen yere geçer (Spotify Connect gibi).
 */
class DevicesActivity : Activity() {
    private lateinit var scroll: ScrollView
    private lateinit var list: LinearLayout
    private val update = { render() }

    private fun dp(v: Float) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, resources.displayMetrics).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(22f), dp(30f), dp(22f), dp(46f)) }
        scroll = ScrollView(this).apply { setBackgroundColor(Color.BLACK); addView(list) }
        setContentView(scroll)
        scroll.post { scroll.requestFocus() }
        Remote.start(this)
    }

    override fun onResume() {
        super.onResume()
        Net.acquire(this)  // ekran açıkken internet (Wi-Fi): arama, kapaklar, hesaptaki cihazlar
        Remote.listen(update)
        Link.listen(update)
        render()
    }

    override fun onPause() {
        super.onPause()
        Net.release(this)
        Remote.unlisten(update)
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
            text = "Nerede çalsın?"; textSize = 15f; setTextColor(Color.WHITE); gravity = Gravity.CENTER
            setTypeface(typeface, Typeface.BOLD)
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8f) })
        val where = Where.get(this)
        val localSub = LocalPlayer.current?.let { "${it.optString("title")}${if (LocalPlayer.playing) " · çalıyor" else ""}" } ?: "Wi-Fi'dan ya da indirilenlerden"
        row("⌚", "Bu saat", localSub, where == "watch") { pick("watch") }
        val phone = Link.now
        val phoneSub = when {
            Link.phoneReachable == false -> "Bulunamadı"
            phone != null && phone.optString("id").isNotEmpty() -> "${phone.optString("title")}${if (phone.optBoolean("playing")) " · çalıyor" else ""}"
            else -> "Bluetooth ile bağlı"
        }
        row("📱", "Telefon", phoneSub, where == "phone") { pick("phone") }
        if (Remote.devices.isNotEmpty()) header("SOUND hesabındaki cihazlar")
        for (d in Remote.devices) {
            val id = d.optString("id")
            val np = Remote.np(id)
            val sub = np?.optJSONObject("track")?.let { "${it.optString("title")}${if (np.optBoolean("playing")) " · çalıyor" else ""}" } ?: "Açık"
            val icon = when (d.optString("kind")) { "phone" -> "📱"; "watch" -> "⌚"; else -> "💻" }
            row(icon, d.optString("name"), sub, where == "dev:$id") { pick("dev:$id") }
        }
        val note = when {
            !Remote.available -> "Bilgisayardaki SOUND'u buradan kumanda etmek için telefonda SOUND hesabına gir; saat bağlantıyı telefondan alır."
            !Remote.connected -> "Hesaptaki cihazlara bağlanıyor…"
            Remote.devices.isEmpty() -> "Hesabında açık başka SOUND yok."
            else -> null
        }
        if (note != null) list.addView(TextView(this).apply {
            text = note; textSize = 12f; setTextColor(0xFFB0B0B8.toInt()); gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10f) })
    }

    private fun header(s: String) {
        list.addView(TextView(this).apply {
            text = s.uppercase(java.util.Locale.forLanguageTag("tr")); textSize = 11f; letterSpacing = 0.06f
            setTextColor(0xFFB49BFF.toInt()); setTypeface(typeface, Typeface.BOLD); gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(10f); bottomMargin = dp(4f) })
    }

    private fun row(icon: String, title: String, sub: String, on: Boolean, onClick: () -> Unit) {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14f), dp(9f), dp(14f), dp(9f))
            background = GradientDrawable().apply { cornerRadius = dp(24f).toFloat(); setColor(if (on) 0xFF3A2C66.toInt() else 0xFF1E1E22.toInt()) }
            isClickable = true
            setOnClickListener { performHapticFeedback(HapticFeedbackConstants.CONTEXT_CLICK); onClick() }
        }
        box.addView(TextView(this).apply { text = icon; textSize = 16f }, LinearLayout.LayoutParams(-2, -2).apply { marginEnd = dp(10f) })
        val texts = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        texts.addView(TextView(this).apply {
            text = title; textSize = 14f; setTextColor(Color.WHITE); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
            setTypeface(typeface, Typeface.BOLD)
        })
        texts.addView(TextView(this).apply {
            text = sub; textSize = 11.5f; setTextColor(if (on) 0xFFD9CCFF.toInt() else 0xFFB8B8C0.toInt()); maxLines = 1; ellipsize = TextUtils.TruncateAt.END
        })
        box.addView(texts, LinearLayout.LayoutParams(0, -2, 1f))
        list.addView(box, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(5f) })
    }

    /** Yeni yeri seç; şu an çalan yerdeki şarkı oraya geçer. */
    private fun pick(target: String) {
        val from = Where.get(this)
        if (from == target) return finish()
        if (target == "phone" && Link.phoneReachable == false) {
            Toast.makeText(this, "Telefon bulunamadı", Toast.LENGTH_SHORT).show()
            Link.start(this)
            return
        }
        val fromDevice = from.takeIf { it.startsWith("dev:") }?.removePrefix("dev:")
        val toDevice = target.takeIf { it.startsWith("dev:") }?.removePrefix("dev:")
        val phone = Link.now?.takeIf { it.optString("id").isNotEmpty() && it.optBoolean("playing") }
        val remoteNp = fromDevice?.let { Remote.np(it) }?.takeIf { it.optBoolean("playing") }
        when (target) {
            "watch" -> {
                Py.warm(this)
                when {
                    from == "phone" && phone != null -> {
                        Link.command(this, "pause")
                        LocalPlayer.playTrack(this, Lib.slim(phone).put("duration", phone.optDouble("dur", 0.0).toInt()), Link.position(phone))
                    }
                    fromDevice != null && remoteNp != null -> Remote.cmd(fromDevice, "handoff") { put("to", Remote.me(this@DevicesActivity)) }
                }
                if (!LocalPlayer.headphones(this)) Toast.makeText(this, "Kulaklık bağlı değil: saatin hoparlöründen çalar", Toast.LENGTH_LONG).show()
            }
            "phone" -> {
                val track = LocalPlayer.current
                if (from == "watch" && track != null && LocalPlayer.playing) {
                    LocalPlayer.pause()
                    Link.play(this, JSONObject().put("kind", "track").put("id", track.optString("id")).put("track", Lib.slim(track)))
                }
            }
            else -> if (toDevice != null) when {
                from == "watch" && LocalPlayer.hasTrack && LocalPlayer.playing -> Remote.transferTo(this, toDevice)
                fromDevice != null && remoteNp != null -> Remote.cmd(fromDevice, "handoff") { put("to", toDevice) }
                from == "phone" && phone != null -> {
                    Link.command(this, "pause")
                    Remote.cmd(toDevice, "playlist") { put("tracks", JSONArray().put(Lib.slim(phone))).put("index", 0) }
                }
            }
        }
        Where.set(this, target)
        finish()
    }
}
