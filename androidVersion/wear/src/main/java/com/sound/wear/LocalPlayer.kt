package com.sound.wear

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.MediaPlayer
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
import androidx.media.app.NotificationCompat.MediaStyle
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Saatte telefonsuz çalma. Sıradaki şarkılar listeden gelir; liste bitince akıllı sırayla (watch_main.radio) devam eder.
 * Şarkının sesi önce saate inir (saate indirilmişse hemen çalar), sıradaki şarkı çalarken önceden indirilir.
 */
object LocalPlayer {
    private val main = Handler(Looper.getMainLooper())
    private val listeners = mutableSetOf<() -> Unit>()
    private lateinit var app: Context

    val queue = mutableListOf<JSONObject>()
    var index = -1
        private set
    var loading = false
        private set
    var error: String? = null
        private set
    var art: Bitmap? = null
        private set
    private var artId: String? = null
    private var player: MediaPlayer? = null
    private var preparedId: String? = null
    private var wantPlay = false
    private var token = 0
    private var extending = false
    private var focus: AudioFocusRequest? = null

    fun listen(listener: () -> Unit) { listeners += listener }
    fun unlisten(listener: () -> Unit) { listeners -= listener }
    private fun changed() {
        listeners.toList().forEach { it() }
        Remote.localChanged()
        if (::app.isInitialized) {
            PlayerService.refresh(app)
            runCatching { androidx.wear.tiles.TileService.getUpdater(app).requestUpdate(NowTile::class.java) }
        }
    }

    fun init(context: Context) {
        if (::app.isInitialized) return
        app = context.applicationContext
        restore()
    }

    val current: JSONObject? get() = queue.getOrNull(index)
    val hasTrack get() = current != null
    val playing get() = wantPlay

    fun position(): Double = runCatching { if (preparedId == current?.optString("id")) (player?.currentPosition ?: 0) / 1000.0 else 0.0 }.getOrDefault(0.0)

    /** Şimdi Çalıyor ekranı ve kart için telefonun /sound/now biçiminde durum. */
    fun state(): JSONObject? {
        val t = current ?: return null
        val dur = runCatching { if (preparedId == t.optString("id")) (player?.duration ?: 0) / 1000.0 else 0.0 }.getOrDefault(0.0)
        return JSONObject()
            .put("id", t.optString("id"))
            .put("title", t.optString("title"))
            .put("artist", t.optString("artist"))
            .put("dur", if (dur > 0) dur else t.optDouble("duration", 0.0))
            .put("pos", position())
            .put("playing", wantPlay && !loading)
            .put("loading", loading)
            .put("error", error ?: "")
            .put("liked", Lib.isLiked(app, t.optString("id")))
            .put("accent", Link.cached(app)?.optString("accent") ?: "#8b5cf6")
            .put("at", System.currentTimeMillis())
            .put("local", true)
    }

    // ---------- komutlar ----------

    fun playList(context: Context, tracks: JSONArray, start: Int = 0, at: Double = 0.0) {
        init(context)
        queue.clear()
        for (i in 0 until tracks.length()) tracks.optJSONObject(i)?.let { if (it.optString("id").isNotEmpty()) queue += Lib.slim(it) }
        if (queue.isEmpty()) return
        index = start.coerceIn(0, queue.size - 1)
        wantPlay = true
        PlayerService.start(app)
        load(at)
    }

    fun playTrack(context: Context, track: JSONObject, at: Double = 0.0) = playList(context, JSONArray().put(track), 0, at)

    fun toggle(context: Context) {
        init(context)
        if (wantPlay) pause() else play(context)
    }

    fun play(context: Context) {
        init(context)
        if (!hasTrack) return
        wantPlay = true
        PlayerService.start(app)
        val p = player
        if (p != null && preparedId == current?.optString("id") && !loading) {
            if (requestFocus()) p.start()
            changed()
        } else load(lastPosition)
    }

    fun pause() {
        wantPlay = false
        runCatching { if (player?.isPlaying == true) player?.pause() }
        lastPosition = position()
        save()
        changed()
    }

    fun next(context: Context, auto: Boolean = false) {
        init(context)
        if (index + 1 >= queue.size) {
            if (!extending) extend { if (index + 1 < queue.size) { index++; load(0.0) } else { wantPlay = false; changed() } }
            return
        }
        index++
        wantPlay = true
        load(0.0)
    }

    fun previous(context: Context) {
        init(context)
        if (position() > 4 || index == 0) { runCatching { player?.seekTo(0) }; changed(); return }
        index--
        load(0.0)
    }

    fun seek(at: Double) {
        if (preparedId == current?.optString("id")) runCatching { player?.seekTo((at * 1000).toInt()) }
        else lastPosition = at
        changed()
    }

    fun jump(context: Context, i: Int) {
        init(context)
        if (i !in queue.indices) return
        index = i
        wantPlay = true
        load(0.0)
    }

    fun stop() {
        wantPlay = false
        token++
        runCatching { player?.release() }
        player = null
        preparedId = null
        abandonFocus()
        save()
        changed()
    }

    // ---------- yükleme ----------

    private var lastPosition = 0.0

    private fun load(at: Double) {
        val track = current ?: return
        val my = ++token
        loading = true
        error = null
        runCatching { player?.reset() }
        preparedId = null
        changed()
        fetchArt(track)
        save()
        Py.pool.execute {
            val result = Py.call(app, "fetch", track.toString(), false)
            main.post {
                if (my != token) return@post
                val path = result.optString("path")
                if (path.isEmpty()) return@post failed(track, result)
                start(track, path, at)
                prefetch()
            }
        }
        if (index >= queue.size - 2) extend {}
    }

    private fun start(track: JSONObject, path: String, at: Double) {
        val p = player ?: MediaPlayer().also { player = it }
        runCatching {
            p.reset()
            p.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            p.setWakeMode(app, PowerManager.PARTIAL_WAKE_LOCK)
            p.setDataSource(path)
            p.prepare()
            if (at > 1) p.seekTo((at * 1000).toInt())
            p.setOnCompletionListener { lastPosition = 0.0; next(app, auto = true) }
            p.setOnErrorListener { _, what, extra -> Log.w("SOUND", "Çalma hatası $what/$extra"); error = "Çalınamadı"; next(app, auto = true); true }
            preparedId = track.optString("id")
            loading = false
            if (wantPlay && requestFocus()) p.start()
            changed()
        }.onFailure {
            Log.w("SOUND", "Dosya açılamadı", it)
            failed(track, JSONObject().put("error", "Dosya açılamadı"))
        }
    }

    /** Şarkı gelmedi. İnternet yoksa saate indirilmiş bir sonraki şarkıya geçilir; yoksa durulur. Şarkı bozuksa atlanır. */
    private fun failed(track: JSONObject, result: JSONObject) {
        loading = false
        error = result.optString("error", "Çalınamadı")
        if (result.optBoolean("network")) {
            val offline = Offline.ids(app)
            val next = (index + 1 until queue.size).firstOrNull { queue[it].optString("id") in offline }
            if (next != null) { index = next; load(0.0); return }
            wantPlay = false
            changed()
            return
        }
        changed()
        val my = token
        main.postDelayed({ if (my == token && wantPlay) next(app, auto = true) }, 1500)
    }

    /** Sıradaki şarkı çalarken önden indir: geçiş beklemesin, internet giderse de bir şarkı daha çalabilsin. */
    private fun prefetch() {
        val upcoming = queue.drop(index + 1).take(2).map { it.toString() }
        if (upcoming.isEmpty()) return
        Py.pool.execute {
            upcoming.forEach { Py.call(app, "fetch", it, false) }
            Py.raw(app, "trim", 400)
        }
    }

    /** Liste bitmek üzere: çalan şarkıya benzeyenleri ekle (telefon/masaüstündeki akıllı sıra). */
    private fun extend(then: () -> Unit) {
        val seed = current ?: return then()
        if (extending) return
        extending = true
        val context = JSONArray(queue.subList(maxOf(0, index - 2), index).map { it.toString() }.map(::JSONObject))
        val exclude = JSONArray(queue.map { it.optString("id") })
        Py.async(app, "radio", seed.toString(), context.toString(), exclude.toString()) { result ->
            extending = false
            val tracks = result.optJSONArray("tracks")
            if (tracks != null) {
                val known = queue.map { it.optString("id") }.toMutableSet()
                for (i in 0 until tracks.length()) {
                    val t = tracks.getJSONObject(i)
                    if (known.add(t.optString("id"))) queue += Lib.slim(t)
                }
                save()
                changed()
            }
            then()
        }
    }

    private fun fetchArt(track: JSONObject) {
        val id = track.optString("id")
        if (artId == id) return
        artId = id
        art = null
        Py.pool.execute {
            val bitmap = runCatching {
                val connection = URL("https://i.ytimg.com/vi/$id/hqdefault.jpg").openConnection() as HttpURLConnection
                connection.connectTimeout = 8000
                connection.readTimeout = 8000
                connection.inputStream.use { BitmapFactory.decodeStream(it) }?.let { square(it) }
            }.getOrNull()
            main.post { if (artId == id) { art = bitmap; changed() } }
        }
    }

    /** YouTube küçük resmi 4:3 ve üstte/altta siyah şeritli: ortadaki kare alınır. */
    private fun square(b: Bitmap): Bitmap {
        val side = minOf(b.width, b.height * 3 / 4)
        return Bitmap.createBitmap(b, (b.width - side) / 2, (b.height - side) / 2, side, side)
    }

    // ---------- ses odağı ----------

    private fun requestFocus(): Boolean {
        val am = app.getSystemService(AudioManager::class.java)
        val request = focus ?: AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            .setOnAudioFocusChangeListener { change ->
                when (change) {
                    AudioManager.AUDIOFOCUS_LOSS, AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> if (wantPlay) pause()
                }
            }
            .build().also { focus = it }
        return am.requestAudioFocus(request) != AudioManager.AUDIOFOCUS_REQUEST_FAILED
    }

    private fun abandonFocus() {
        focus?.let { app.getSystemService(AudioManager::class.java).abandonAudioFocusRequest(it) }
    }

    /** Saate Bluetooth kulaklık bağlı mı (değilse saatin hoparlöründen çalar). */
    fun headphones(context: Context): Boolean = context.getSystemService(AudioManager::class.java)
        .getDevices(AudioManager.GET_DEVICES_OUTPUTS)
        .any { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_A2DP || it.type == AudioDeviceInfo.TYPE_BLE_HEADSET || it.type == AudioDeviceInfo.TYPE_BLE_SPEAKER }

    // ---------- kalıcılık: süreç kapanınca kart ve kulaklık düğmesi kaldığı yerden sürdürsün ----------

    private fun save() {
        if (!::app.isInitialized) return
        val tracks = JSONArray()
        queue.takeLast(200).forEach { tracks.put(it) }
        val shift = maxOf(0, queue.size - 200)
        app.getSharedPreferences("sound", Context.MODE_PRIVATE).edit()
            .putString("local_queue", tracks.toString())
            .putInt("local_index", index - shift)
            .putFloat("local_pos", (if (preparedId != null) position() else lastPosition).toFloat())
            .apply()
    }

    private fun restore() {
        val prefs = app.getSharedPreferences("sound", Context.MODE_PRIVATE)
        val tracks = runCatching { JSONArray(prefs.getString("local_queue", "[]")) }.getOrDefault(JSONArray())
        for (i in 0 until tracks.length()) queue += tracks.getJSONObject(i)
        index = prefs.getInt("local_index", -1).coerceAtMost(queue.size - 1)
        lastPosition = prefs.getFloat("local_pos", 0f).toDouble()
        current?.let { fetchArt(it) }
    }
}

/**
 * Saatte çalarken ön plan hizmeti: ekran kapansa da müzik sürer. Medya oturumu kulaklık düğmelerini ve Wear OS'un medya
 * denetimlerini bağlar. Duraklatılınca 10 dakika sonra kendini kapatır; çalarken Wi-Fi tutulur.
 */
class PlayerService : Service() {
    private lateinit var session: MediaSessionCompat
    private val main = Handler(Looper.getMainLooper())
    private val idle = Runnable { if (!LocalPlayer.playing) stopSelf() }
    private var netHeld = false
    private val noisy = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) { if (LocalPlayer.playing) LocalPlayer.pause() }  // kulaklık çıktı
    }

    companion object {
        private const val CHANNEL = "playback"
        private const val ID = 7
        @Volatile private var instance: PlayerService? = null

        fun start(context: Context) {
            if (instance != null) return refresh(context)
            runCatching { context.startForegroundService(Intent(context, PlayerService::class.java)) }
                .onFailure { Log.w("SOUND", "Çalma hizmeti başlatılamadı", it) }
        }

        fun refresh(context: Context) { instance?.update() }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        LocalPlayer.init(this)
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, "Çalma", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) })
        session = MediaSessionCompat(this, "SOUNDwatch").apply {
            setCallback(object : MediaSessionCompat.Callback() {
                override fun onPlay() = LocalPlayer.play(this@PlayerService)
                override fun onPause() = LocalPlayer.pause()
                override fun onSkipToNext() = LocalPlayer.next(this@PlayerService)
                override fun onSkipToPrevious() = LocalPlayer.previous(this@PlayerService)
                override fun onStop() = LocalPlayer.pause()
            })
            isActive = true
        }
        registerReceiver(noisy, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY))
        ServiceCompat.startForeground(this, ID, notification(), if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else 0)
        Net.acquire(this)
        netHeld = true
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ServiceCompat.startForeground(this, ID, notification(), if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else 0)
        update()
        return START_NOT_STICKY
    }

    fun update() {
        main.post {
            val s = LocalPlayer.state()
            val playing = LocalPlayer.playing
            session.setPlaybackState(PlaybackStateCompat.Builder()
                .setActions(PlaybackStateCompat.ACTION_PLAY or PlaybackStateCompat.ACTION_PAUSE or PlaybackStateCompat.ACTION_PLAY_PAUSE or
                    PlaybackStateCompat.ACTION_SKIP_TO_NEXT or PlaybackStateCompat.ACTION_SKIP_TO_PREVIOUS)
                .setState(if (playing) PlaybackStateCompat.STATE_PLAYING else PlaybackStateCompat.STATE_PAUSED, (LocalPlayer.position() * 1000).toLong(), 1f)
                .build())
            session.setMetadata(MediaMetadataCompat.Builder()
                .putString(MediaMetadataCompat.METADATA_KEY_TITLE, s?.optString("title") ?: "SOUND")
                .putString(MediaMetadataCompat.METADATA_KEY_ARTIST, s?.optString("artist") ?: "")
                .putLong(MediaMetadataCompat.METADATA_KEY_DURATION, ((s?.optDouble("dur", 0.0) ?: 0.0) * 1000).toLong())
                .putBitmap(MediaMetadataCompat.METADATA_KEY_ALBUM_ART, LocalPlayer.art)
                .build())
            runCatching { getSystemService(NotificationManager::class.java).notify(ID, notification()) }
            main.removeCallbacks(idle)
            if (!playing) main.postDelayed(idle, 10 * 60 * 1000L)
        }
    }

    private fun notification(): Notification {
        val s = LocalPlayer.state()
        val open = PendingIntent.getActivity(this, 0, Intent(this, NowActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_note)
            .setContentTitle(s?.optString("title") ?: "SOUND")
            .setContentText(s?.optString("artist") ?: "")
            .setLargeIcon(LocalPlayer.art)
            .setContentIntent(open)
            .setOngoing(LocalPlayer.playing)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_TRANSPORT)
            .setStyle(MediaStyle().setMediaSession(session.sessionToken))
            .build()
    }

    override fun onDestroy() {
        instance = null
        main.removeCallbacks(idle)
        runCatching { unregisterReceiver(noisy) }
        if (LocalPlayer.playing) LocalPlayer.pause()
        session.release()
        if (netHeld) Net.release(this)
        super.onDestroy()
    }
}
