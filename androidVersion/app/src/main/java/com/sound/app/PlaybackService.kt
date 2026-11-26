package com.sound.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.media.app.NotificationCompat.MediaStyle
import com.chaquo.python.Python
import org.json.JSONObject
import java.net.URL
import kotlin.concurrent.thread

/**
 * Müzik uygulama arka plandayken sürsün diye ön plan hizmeti: bildirim, kilit ekranı ve kulaklık düğmeleri.
 * Sesi WebView çalar; hizmet süreci ayakta tutar ve düğmeleri arayüze iletir.
 *
 * Android 12'den beri arka plandaki uygulama ön plan hizmetini yeniden başlatamaz. Bu yüzden hizmet şarkı aralarında ve
 * kısa duraklamalarda ön planda kalır; yalnızca uzun duraklamadan sonra ön plandan çıkar.
 *
 * Uygulama kapalıyken kulaklık bağlanınca (HeadsetReceiver) ya da kulaklığın çal düğmesine basılınca (MediaKeyReceiver)
 * hizmet motoru (Engine) ekransız başlatır ve son şarkıyı kaldığı yerden çalar.
 */
class PlaybackService : Service() {
    private lateinit var session: MediaSessionCompat
    private lateinit var wakeLock: PowerManager.WakeLock
    private lateinit var wifiLock: WifiManager.WifiLock
    private val main = Handler(Looper.getMainLooper())
    private var artId: String? = null
    private var art: Bitmap? = null
    private var title = "SOUND"
    private var artist = ""
    private var playing = false
    private var base: String? = null
    private var trackId: String? = null
    private var released = false   // uzun duraklama: ön plandan çıkıldı
    private var destroyed = false

    private val releaseForeground = Runnable {
        released = true
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_DETACH)
    }
    private val releaseLocks = Runnable { setLocks(false) }

    /** Kulaklık çıkarıldı / bağlantısı koptu: müzik hoparlörden çalmasın. */
    private val noisy = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY && playing && Prefs.headsetPause(context)) send("pause")
        }
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Çalan şarkı", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) },
        )
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "SOUND:playback").apply { setReferenceCounted(false) }
        @Suppress("DEPRECATION")
        wifiLock = applicationContext.getSystemService(WifiManager::class.java)
            .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "SOUND:playback").apply { setReferenceCounted(false) }
        session = MediaSessionCompat(this, "SOUND").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                // Sistem "çal" ya da "duraklat" der: durumu tersine çevirmek çalan şarkıyı durdurabilirdi
                override fun onPlay() = send("play")
                override fun onPause() = send("pause")
                override fun onStop() = send("pause")
                override fun onSkipToNext() = send("next")
                override fun onSkipToPrevious() = send("previous")
            })
            // uygulama kapatıldıktan sonra kulaklık düğmesi bize gelsin (MediaKeyReceiver motoru başlatır)
            val keys = Intent(Intent.ACTION_MEDIA_BUTTON).setComponent(ComponentName(this@PlaybackService, MediaKeyReceiver::class.java))
            // sistem tuş bilgisini (EXTRA_KEY_EVENT) niyete ekler: değiştirilebilir olmalı
            val mutable = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
            setMediaButtonReceiver(PendingIntent.getBroadcast(this@PlaybackService, 0, keys, mutable or PendingIntent.FLAG_UPDATE_CURRENT))
            isActive = true
        }
        ContextCompat.registerReceiver(this, noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY), ContextCompat.RECEIVER_NOT_EXPORTED)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        released = false  // bu çağrıdan sonra ön plana geçmek zorunlu ve izinli
        if (intent?.getBooleanExtra(EXTRA_BOOT, false) == true) {
            show()  // ön plana hemen geçilmeli (5 sn sınırı)
            boot(intent.getStringExtra(EXTRA_ACTION) ?: "play")
            return START_NOT_STICKY
        }
        intent?.getStringExtra(EXTRA_ACTION)?.let { send(it) }
        if (intent != null && intent.hasExtra(EXTRA_PLAYING)) {
            applyState(
                intent.getBooleanExtra(EXTRA_PLAYING, false),
                intent.getStringExtra(EXTRA_TITLE) ?: "SOUND",
                intent.getStringExtra(EXTRA_ARTIST) ?: "",
                intent.getStringExtra(EXTRA_ID),
                intent.getStringExtra(EXTRA_BASE),
            )
        } else show()
        return START_NOT_STICKY
    }

    /** Kulaklık bağlandı ya da kulaklık düğmesine basıldı; uygulama kapalı olabilir. */
    private fun boot(action: String) {
        val wasRunning = Engine.running && Engine.loaded
        if (wasRunning && action != "headset") { send(action); return }
        Engine.start(this)
        if (action == "headset") {
            if (!wasRunning) { title = "SOUND"; artist = "Kulaklık bağlandı"; show() }
            // ACL bağlantısı ses yolundan önce gelir: ses kulaklığa geçmeden çalarsa hoparlörden duyulur
            waitForHeadset(HEADSET_WAIT_STEPS) { ready -> if (ready) Engine.resume { ok -> if (!ok) giveUp() } else giveUp() }
        } else {
            Engine.resume { ok -> if (!ok) giveUp() }
        }
    }

    private fun waitForHeadset(steps: Int, done: (Boolean) -> Unit) {
        if (AudioOutputs.hasHeadset(this)) { main.postDelayed({ done(true) }, 800); return }
        if (steps <= 0) { done(false); return }
        main.postDelayed({ if (!destroyed) waitForHeadset(steps - 1, done) }, 500)
    }

    /** Çalınacak şarkı yok ya da kulaklık sese hiç bağlanmadı: ekran da kapalıysa her şey kapanır. */
    private fun giveUp() {
        if (destroyed || playing) return
        if (Engine.activity == null) {
            Engine.shutdown()
            stopSelf()
        } else {
            title = "SOUND"; artist = ""
            main.post(releaseForeground)
        }
    }

    private fun applyState(playing: Boolean, title: String, artist: String, id: String?, base: String?) {
        this.playing = playing
        this.title = title
        this.artist = artist
        trackId = id
        this.base = base
        main.removeCallbacks(releaseForeground)
        main.removeCallbacks(releaseLocks)
        if (playing) {
            released = false
            setLocks(true)
        } else {
            main.postDelayed(releaseLocks, LOCK_GRACE_MS)  // şarkı arasında telefon uyumasın, sıradaki hazırlansın
            if (!released) main.postDelayed(releaseForeground, FOREGROUND_GRACE_MS)
        }
        show()
        if (trackId != artId) loadArt()
    }

    private fun setLocks(on: Boolean) {
        runCatching {
            if (on) {
                if (!wakeLock.isHeld) wakeLock.acquire()
                if (!wifiLock.isHeld) wifiLock.acquire()
            } else {
                if (wakeLock.isHeld) wakeLock.release()
                if (wifiLock.isHeld) wifiLock.release()
            }
        }.onFailure { Log.w("SOUND", "Çalma kilitleri", it) }
    }

    private fun send(action: String) {
        thread {
            runCatching { Python.getInstance().getModule("android_main").callAttr("command", action) }
                .onFailure { Log.e("SOUND", "Komut iletilemedi: $action", it) }
        }
    }

    private fun button(icon: Int, label: String, action: String, code: Int) = NotificationCompat.Action(
        icon, label,
        PendingIntent.getService(
            this, code, Intent(this, PlaybackService::class.java).putExtra(EXTRA_ACTION, action),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        ),
    )

    private fun show() {
        if (destroyed) return
        session.setMetadata(
            MediaMetadataCompat.Builder()
                .putString(MediaMetadataCompat.METADATA_KEY_TITLE, title)
                .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, artist)
                .putBitmap(MediaMetadataCompat.METADATA_KEY_ALBUM_ART, art)
                .build(),
        )
        session.setPlaybackState(
            PlaybackStateCompat.Builder()
                .setActions(
                    PlaybackStateCompat.ACTION_PLAY or PlaybackStateCompat.ACTION_PAUSE or PlaybackStateCompat.ACTION_PLAY_PAUSE or
                        PlaybackStateCompat.ACTION_SKIP_TO_NEXT or PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS,
                )
                .setState(
                    if (playing) PlaybackStateCompat.STATE_PLAYING else PlaybackStateCompat.STATE_PAUSED,
                    PlaybackStateCompat.PLAYBACK_POSITION_UNKNOWN, 1f,
                )
                .build(),
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_note)
            .setContentTitle(title)
            .setContentText(artist)
            .setLargeIcon(art)
            .setContentIntent(open)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setOnlyAlertOnce(true)
            .setOngoing(playing)
            .addAction(button(R.drawable.ic_prev, "Önceki", "previous", 1))
            .addAction(if (playing) button(R.drawable.ic_pause, "Duraklat", "toggle", 2) else button(R.drawable.ic_play, "Çal", "toggle", 2))
            .addAction(button(R.drawable.ic_next, "Sonraki", "next", 3))
            .setStyle(MediaStyle().setMediaSession(session.sessionToken).setShowActionsInCompactView(0, 1, 2))
            .build()
        if (released) {
            getSystemService(NotificationManager::class.java).notify(NOTIFICATION, notification)
            return
        }
        val type = if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else 0
        // Arka planda izin verilmezse uygulama düşmesin: bildirim yine güncellenir
        runCatching { ServiceCompat.startForeground(this, NOTIFICATION, notification, type) }.onFailure {
            Log.w("SOUND", "Ön plana geçilemedi", it)
            getSystemService(NotificationManager::class.java).notify(NOTIFICATION, notification)
        }
    }

    private fun loadArt() {
        val id = trackId ?: return
        val root = base ?: return
        artId = id
        thread {
            val bitmap = runCatching {
                val connection = URL("$root/thumb/$id").openConnection().apply { connectTimeout = 10_000; readTimeout = 10_000 }
                connection.getInputStream().use { BitmapFactory.decodeStream(it) }?.let { scaled(it) }
            }.getOrNull()
            if (bitmap != null) main.post {
                if (!destroyed && id == trackId) {
                    art = bitmap
                    show()
                    WatchLink.publishArt(this, id, bitmap)  // saatteki çalan şarkı ekranı
                }
            }
        }
    }

    /** Büyük kapak bildirim ve oturum üzerinden sisteme gönderilirken sınırı aşabilir. */
    private fun scaled(bitmap: Bitmap): Bitmap {
        val longest = maxOf(bitmap.width, bitmap.height)
        if (longest <= ART_SIZE) return bitmap
        return Bitmap.createScaledBitmap(bitmap, bitmap.width * ART_SIZE / longest, bitmap.height * ART_SIZE / longest, true)
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // kullanıcı uygulamayı son uygulamalardan kapattı: ses motorla birlikte durur
        Engine.shutdown()
        stopSelf()
    }

    override fun onDestroy() {
        destroyed = true
        instance = null
        main.removeCallbacksAndMessages(null)
        setLocks(false)
        runCatching { unregisterReceiver(noisy) }
        session.release()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val CHANNEL = "playback"
        private const val NOTIFICATION = 1
        private const val EXTRA_ACTION = "action"
        private const val EXTRA_PLAYING = "playing"
        private const val EXTRA_TITLE = "title"
        private const val EXTRA_ARTIST = "artist"
        private const val EXTRA_ID = "id"
        private const val EXTRA_BASE = "base"
        private const val EXTRA_BOOT = "boot"
        private const val HEADSET_WAIT_STEPS = 30  // 15 sn
        private const val ART_SIZE = 512
        private const val LOCK_GRACE_MS = 30_000L
        private const val FOREGROUND_GRACE_MS = 10 * 60_000L
        private var instance: PlaybackService? = null

        /** Arayüz süreci ölürse çalmanın sürdürülüp sürdürülmeyeceğini söyler. */
        val isPlaying: Boolean get() = instance?.playing == true

        /** Kulaklık bağlandı / kulaklık düğmesi: uygulama kapalı olsa da hizmeti başlatır (sistem bu durumlarda izin verir). */
        fun command(context: Context, action: String) {
            val intent = Intent(context, PlaybackService::class.java).putExtra(EXTRA_ACTION, action).putExtra(EXTRA_BOOT, true)
            runCatching { ContextCompat.startForegroundService(context, intent) }
                .onFailure { Log.w("SOUND", "Çalma hizmeti başlatılamadı ($action)", it) }
        }

        /** Arayüzdeki çalma durumu değişti. Hizmet ilk çalmada başlar, sonra doğrudan güncellenir (ana iş parçacığında çağrılır). */
        fun update(context: Context, state: JSONObject, pageUrl: String?) {
            val track = state.optJSONObject("track") ?: return
            val playing = state.optBoolean("playing") || state.optBoolean("loading")
            val base = pageUrl?.substringBeforeLast("/")
            val service = instance
            if (service != null) {
                service.applyState(playing, track.optString("title"), track.optString("artist"), track.optString("id"), base)
                return
            }
            if (!playing) return
            val intent = Intent(context, PlaybackService::class.java)
                .putExtra(EXTRA_PLAYING, true)
                .putExtra(EXTRA_TITLE, track.optString("title"))
                .putExtra(EXTRA_ARTIST, track.optString("artist"))
                .putExtra(EXTRA_ID, track.optString("id"))
                .putExtra(EXTRA_BASE, base)
            runCatching { ContextCompat.startForegroundService(context, intent) }
                .onFailure { Log.w("SOUND", "Çalma hizmeti başlatılamadı", it) }
        }
    }
}
