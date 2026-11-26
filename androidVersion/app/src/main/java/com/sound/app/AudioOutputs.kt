package com.sound.app

import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaRouter2
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/**
 * Ses çıkışları: telefon hoparlörü, kablolu kulaklık, Bluetooth (Galaxy Buds2 gibi). Hangisinden ses çıktığını söyler,
 * değişince arayüze bildirir; kulaklık bağlanınca (ayar açıksa) çalmayı sürdürür.
 */
object AudioOutputs {
    private val HEADSETS = setOf(
        AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_WIRED_HEADPHONES, AudioDeviceInfo.TYPE_BLUETOOTH_A2DP,
        AudioDeviceInfo.TYPE_USB_HEADSET, AudioDeviceInfo.TYPE_HEARING_AID, AudioDeviceInfo.TYPE_BLE_HEADSET,
        AudioDeviceInfo.TYPE_BLE_SPEAKER, AudioDeviceInfo.TYPE_BLE_BROADCAST,
    )
    private val BLUETOOTH = setOf(
        AudioDeviceInfo.TYPE_BLUETOOTH_A2DP, AudioDeviceInfo.TYPE_HEARING_AID, AudioDeviceInfo.TYPE_BLE_HEADSET,
        AudioDeviceInfo.TYPE_BLE_SPEAKER, AudioDeviceInfo.TYPE_BLE_BROADCAST,
    )
    private val SHOWN = HEADSETS + AudioDeviceInfo.TYPE_BUILTIN_SPEAKER
    private val main = Handler(Looper.getMainLooper())
    private var watching = false
    private var registeredAt = 0L

    private fun manager(context: Context) = context.getSystemService(AudioManager::class.java)

    fun outputs(context: Context): List<AudioDeviceInfo> {
        val seen = mutableSetOf<String>()
        // Bir Bluetooth kulaklık birkaç kez görünebilir (ör. LE Audio'da kulaklık + hoparlör): ada ve türe göre tekilleştirilir
        return manager(context).getDevices(AudioManager.GET_DEVICES_OUTPUTS)
            .filter { it.type in SHOWN && it.isSink }
            .filter { seen.add("${kind(it)}|${it.productName}") }
    }

    fun hasHeadset(context: Context) = outputs(context).any { it.type in HEADSETS }

    fun hasBluetoothAudio(context: Context) = outputs(context).any { it.type in BLUETOOTH }

    /** Müziğin şu an çıktığı cihaz. Android 13+ sistem söyler; öncesinde öncelik sırası: Bluetooth > USB > kablolu > hoparlör. */
    fun current(context: Context, list: List<AudioDeviceInfo> = outputs(context)): AudioDeviceInfo? {
        if (Build.VERSION.SDK_INT >= 33) {
            val media = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).build()
            val routed = runCatching { manager(context).getAudioDevicesForAttributes(media) }.getOrNull().orEmpty()
            for (device in routed) {
                list.firstOrNull { it.id == device.id }?.let { return it }
                list.firstOrNull { it.type == device.type && it.productName == device.productName }?.let { return it }
            }
        }
        fun rank(d: AudioDeviceInfo) = when (d.type) {
            in BLUETOOTH -> 0
            AudioDeviceInfo.TYPE_USB_HEADSET -> 1
            AudioDeviceInfo.TYPE_WIRED_HEADSET, AudioDeviceInfo.TYPE_WIRED_HEADPHONES -> 2
            else -> 3
        }
        return list.minByOrNull(::rank)
    }

    private fun kind(d: AudioDeviceInfo) = when (d.type) {
        AudioDeviceInfo.TYPE_BUILTIN_SPEAKER -> "speaker"
        in BLUETOOTH -> "bluetooth"
        AudioDeviceInfo.TYPE_USB_HEADSET -> "usb"
        else -> "headphones"
    }

    private fun name(d: AudioDeviceInfo): String {
        val product = d.productName?.toString()?.trim().orEmpty()
        return when (kind(d)) {
            "speaker" -> "Telefon hoparlörü"
            "bluetooth" -> product.ifEmpty { "Bluetooth kulaklık" }
            "usb" -> product.ifEmpty { "USB kulaklık" }
            else -> "Kablolu kulaklık"
        }
    }

    /** Arayüz için: {"current": {...}, "outputs": [{"id","name","kind","active"}], "switch": true} */
    fun state(context: Context): JSONObject {
        val list = outputs(context)
        val now = current(context, list)
        val items = JSONArray()
        var active: JSONObject? = null
        for (d in list) {
            val item = JSONObject().put("id", d.id.toString()).put("name", name(d)).put("kind", kind(d)).put("active", d.id == now?.id)
            if (d.id == now?.id) active = item
            items.put(item)
        }
        return JSONObject().put("outputs", items).put("current", active ?: JSONObject.NULL).put("switch", true)
    }

    /** Değişiklikleri dinler (bir kez kurulur). Kurulurken sistem mevcut cihazları da "eklendi" diye bildirir: o atlanır. */
    fun watch(context: Context) {
        if (watching) return
        watching = true
        val app = context.applicationContext
        registeredAt = SystemClock.elapsedRealtime()
        manager(app).registerAudioDeviceCallback(object : AudioDeviceCallback() {
            override fun onAudioDevicesAdded(added: Array<out AudioDeviceInfo>) {
                if (SystemClock.elapsedRealtime() - registeredAt < 1000) return
                changed(app)
                if (added.any { it.type in HEADSETS && it.isSink }) Engine.onHeadsetAdded()
            }

            override fun onAudioDevicesRemoved(removed: Array<out AudioDeviceInfo>) = changed(app)
        }, main)
    }

    private val pending = Any()
    private fun changed(app: Context) {
        // yönlendirme cihaz eklendikten biraz sonra değişir: kısa bir gecikmeyle bildirilir
        main.removeCallbacksAndMessages(pending)
        main.postAtTime({ Engine.pushOutputs(state(app)) }, pending, SystemClock.uptimeMillis() + 600)
    }

    /** Sistemin çıkış seçicisi (Android 14+ resmi; 11-13 sistem arayüzünün medya çıkışı penceresi; eskilerde ayarlar paneli). */
    fun openSwitcher(context: Context): Boolean {
        if (Build.VERSION.SDK_INT >= 34) {
            if (runCatching { MediaRouter2.getInstance(context).showSystemOutputSwitcher() }.getOrDefault(false)) return true
        }
        if (Build.VERSION.SDK_INT >= 30) {
            val sent = runCatching {
                context.sendBroadcast(
                    Intent("com.android.systemui.action.LAUNCH_MEDIA_OUTPUT_DIALOG").setPackage("com.android.systemui")
                        .putExtra("package_name", context.packageName),
                )
            }
            if (sent.isSuccess) return true
        }
        val panel = Intent("com.android.settings.panel.action.MEDIA_OUTPUT")
            .putExtra("com.android.settings.panel.extra.PACKAGE_NAME", context.packageName)
        if (start(context, panel)) return true
        return openBluetoothSettings(context)
    }

    fun openBluetoothSettings(context: Context) = start(context, Intent(Settings.ACTION_BLUETOOTH_SETTINGS))

    private fun start(context: Context, intent: Intent): Boolean = runCatching {
        if (context !is MainActivity) intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
    }.onFailure { Log.w("SOUND", "Açılamadı: ${intent.action}", it) }.isSuccess
}
