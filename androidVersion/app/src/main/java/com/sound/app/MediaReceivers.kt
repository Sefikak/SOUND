package com.sound.app

import android.Manifest
import android.bluetooth.BluetoothClass
import android.bluetooth.BluetoothDevice
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.view.KeyEvent
import androidx.core.content.ContextCompat

/**
 * Bluetooth kulaklık bağlandı (uygulama kapalıyken de gelir). Ayar açıksa PlaybackService motoru ekransız başlatır,
 * ses kulaklığa geçince kaldığın yerden çalar. Android 12+ "Yakındaki cihazlar" izni gerekir; bu yayını alan uygulama
 * ön plan hizmeti başlatabilir (sistemin izin verdiği istisna).
 */
class HeadsetReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != BluetoothDevice.ACTION_ACL_CONNECTED || !Prefs.headsetPlay(context)) return
        if (Build.VERSION.SDK_INT >= 31 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED
        ) return
        val device: BluetoothDevice? = if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
        } else {
            @Suppress("DEPRECATION") intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE)
        }
        // saat, klavye, telefon gibi ses cihazı olmayanlar atlanır (sınıfı bilinmiyorsa ses cihazı olabilir, denenir)
        val major = runCatching { device?.bluetoothClass?.majorDeviceClass }.getOrNull()
        if (major != null && major != BluetoothClass.Device.Major.AUDIO_VIDEO && major != BluetoothClass.Device.Major.UNCATEGORIZED) return
        if (PlaybackService.isPlaying) return
        PlaybackService.command(context, "headset")
    }
}

/**
 * Kulaklığın / saatin çal düğmesi, SOUND'un medya oturumu kapalıyken (uygulama kapatılmış) gelirse buraya düşer:
 * motor ekransız başlar ve son şarkı çalar.
 */
class MediaKeyReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_MEDIA_BUTTON) return
        val event: KeyEvent? = if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT, KeyEvent::class.java)
        } else {
            @Suppress("DEPRECATION") intent.getParcelableExtra(Intent.EXTRA_KEY_EVENT)
        }
        if (event == null) { PlaybackService.command(context, "play"); return }  // tuşu bilinmiyor: çal
        if (event.action != KeyEvent.ACTION_DOWN || event.repeatCount > 0) return
        val action = when (event.keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY, KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE, KeyEvent.KEYCODE_HEADSETHOOK -> "play"
            KeyEvent.KEYCODE_MEDIA_NEXT -> "next"
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> "previous"
            else -> return  // duraklat / durdur: zaten çalmıyor
        }
        PlaybackService.command(context, action)
    }
}
