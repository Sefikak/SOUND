package com.sound.app

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Build
import android.os.IBinder
import android.support.v4.media.MediaMetadataCompat
import android.support.v4.media.session.MediaSessionCompat
import android.support.v4.media.session.PlaybackStateCompat
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
 */
class PlaybackService : Service() {
    private lateinit var session: MediaSessionCompat
    private var artId: String? = null
    private var art: Bitmap? = null
    private var title = "SOUND"
    private var artist = ""
    private var playing = false
    private var base: String? = null
    private var trackId: String? = null

    override fun onCreate() {
        super.onCreate()
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Çalan şarkı", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) },
        )
        session = MediaSessionCompat(this, "SOUND").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() = send("toggle")
                override fun onPause() = send("toggle")
                override fun onSkipToNext() = send("next")
                override fun onSkipToPrevious() = send("previous")
            })
            isActive = true
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        intent?.getStringExtra(EXTRA_ACTION)?.let { send(it) }
        if (intent != null && intent.hasExtra(EXTRA_PLAYING)) {
            playing = intent.getBooleanExtra(EXTRA_PLAYING, false)
            title = intent.getStringExtra(EXTRA_TITLE) ?: "SOUND"
            artist = intent.getStringExtra(EXTRA_ARTIST) ?: ""
            trackId = intent.getStringExtra(EXTRA_ID)
            base = intent.getStringExtra(EXTRA_BASE)
        }
        show()
        if (trackId != artId) loadArt()
        return START_NOT_STICKY
    }

    private fun send(action: String) {
        thread { Python.getInstance().getModule("android_main").callAttr("command", action) }
    }

    private fun button(icon: Int, label: String, action: String, code: Int) = NotificationCompat.Action(
        icon, label,
        PendingIntent.getService(
            this, code, Intent(this, PlaybackService::class.java).putExtra(EXTRA_ACTION, action),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        ),
    )

    private fun show() {
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
        val type = if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else 0
        ServiceCompat.startForeground(this, NOTIFICATION, notification, type)
        if (!playing) ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_DETACH)
    }

    private fun loadArt() {
        val id = trackId ?: return
        val root = base ?: return
        artId = id
        thread {
            val bitmap = runCatching { URL("$root/thumb/$id").openStream().use { BitmapFactory.decodeStream(it) } }.getOrNull()
            if (bitmap != null && id == trackId) {
                art = bitmap
                show()
            }
        }
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        stopSelf()  // kullanıcı uygulamayı son uygulamalardan kapattı: ses WebView ile birlikte durur
    }

    override fun onDestroy() {
        running = false
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
        private var running = false

        /** Arayüzdeki çalma durumu değişti. Hizmet ilk çalmada başlar, çalma yokken hiç başlamaz. */
        fun update(context: Context, state: JSONObject, pageUrl: String?) {
            val track = state.optJSONObject("track") ?: return
            val playing = state.optBoolean("playing") || state.optBoolean("loading")
            if (!playing && !running) return
            running = true
            val intent = Intent(context, PlaybackService::class.java)
                .putExtra(EXTRA_PLAYING, playing)
                .putExtra(EXTRA_TITLE, track.optString("title"))
                .putExtra(EXTRA_ARTIST, track.optString("artist"))
                .putExtra(EXTRA_ID, track.optString("id"))
                .putExtra(EXTRA_BASE, pageUrl?.substringBeforeLast("/"))
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }
    }
}
