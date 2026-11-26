package com.sound.app

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.content.MutableContextWrapper
import android.content.pm.ApplicationInfo
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.webkit.ConsoleMessage
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.core.content.pm.PackageInfoCompat
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Çalma motoru: masaüstü SOUND arayüzünü çalıştıran WebView ve Python arka ucu.
 *
 * Ekrandan (MainActivity) bağımsızdır: uygulama kapalıyken kulaklık bağlanınca ya da kulaklığın çal düğmesine basılınca
 * PlaybackService motoru ekransız başlatır, müzik uygulama açılmadan çalar. Uygulama açılınca aynı WebView ekrana takılır
 * (MutableContextWrapper ile bağlamı Activity'ye geçer), şarkı kesilmez.
 */
@SuppressLint("StaticFieldLeak")  // yalnızca uygulama bağlamı ve ekrana takılıyken Activity tutulur
object Engine {
    private const val TAG = "SOUND"
    private const val BLACK = 0xFF000000.toInt()
    private val main = Handler(Looper.getMainLooper())
    val pool: ExecutorService = Executors.newCachedThreadPool()
    private lateinit var app: Context
    private var host: MutableContextWrapper? = null
    private val backend: PyObject by lazy { Python.getInstance().getModule("android_main") }
    private var url: String? = null  // Python bir kez başlar; WebView yeniden kurulursa aynı adres açılır
    private var starting = false

    var web: WebView? = null
        private set
    var loaded = false
        private set
    var activity: MainActivity? = null
        private set

    val running: Boolean get() = web != null

    /** Motoru başlatır (zaten çalışıyorsa bir şey yapmaz). Ana iş parçacığında çağrılır. */
    fun start(context: Context) {
        if (web != null) return
        app = context.applicationContext
        if (app.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) WebView.setWebContentsDebuggingEnabled(true)
        val wrapper = host ?: MutableContextWrapper(app).also { host = it }
        activity?.let { wrapper.baseContext = it }
        web = createWeb(wrapper)
        loaded = false
        AudioOutputs.watch(app)
        val known = url
        if (known != null) {
            web?.loadUrl(known)
        } else if (!starting) {
            starting = true
            val data = app.filesDir.resolve("sound").absolutePath
            pool.execute {
                val address = runCatching { backend.callAttr("start", data, Native).toString() }
                    .onFailure { Log.e(TAG, "Arka uç başlatılamadı", it) }.getOrNull()
                main.post {
                    starting = false
                    url = address
                    if (address != null) web?.loadUrl(address)
                }
            }
        }
    }

    /** Ekran açıldı: WebView onun içine taşınır. */
    fun attach(screen: MainActivity, root: FrameLayout) {
        activity = screen
        host?.baseContext = screen
        val view = web ?: return
        (view.parent as? ViewGroup)?.removeView(view)
        root.addView(view, 0, FrameLayout.LayoutParams(-1, -1))
        if (loaded) screen.hideSplash()
    }

    /** Ekran kapandı: WebView ekrandan ayrılır, müzik (çalıyorsa) sürer. */
    fun detach(screen: MainActivity) {
        if (activity !== screen) return
        web?.let { (it.parent as? ViewGroup)?.removeView(it) }
        host?.baseContext = app
        activity = null
    }

    /** Motoru durdurur (Python süreç boyunca çalışmayı sürdürür, sonraki başlatma hızlıdır). */
    fun shutdown() {
        val view = web ?: return
        (view.parent as? ViewGroup)?.removeView(view)
        view.destroy()
        web = null
        loaded = false
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun createWeb(context: Context) = WebView(context).apply {
        setBackgroundColor(BLACK)
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false  // sıradaki şarkıya kendiliğinden geçebilsin
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        settings.allowFileAccess = false
        setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false)  // ekran kapalıyken de müzik sürsün
        overScrollMode = View.OVER_SCROLL_NEVER
        addJavascriptInterface(Native, "SoundNative")
        webViewClient = Client
        webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                Log.i("SOUNDjs", "${m.message()} @${m.lineNumber()}")
                return true
            }
        }
    }

    /** Arayüz süreci öldü (çoğunlukla bellek yetmedi): yalnızca WebView yenilenir, çalıyorsa şarkı kaldığı yerden sürer. */
    private fun rebuild(dead: WebView) {
        if (dead !== web) return
        val address = dead.url ?: url
        val parent = dead.parent as? ViewGroup
        parent?.removeView(dead)
        dead.destroy()
        val wrapper = host ?: return
        web = createWeb(wrapper)
        loaded = false
        parent?.addView(web, 0, FrameLayout.LayoutParams(-1, -1))
        if (address != null) web?.loadUrl(address)
        if (PlaybackService.isPlaying) resume(RESUME_TRIES)
    }

    /** Sayfa ve oturum yüklenene kadar saniyede bir dener, sonra kaldığı yerden çalar. done(true): çalıyor. */
    fun resume(tries: Int = RESUME_TRIES, done: ((Boolean) -> Unit)? = null) {
        if (tries <= 0) { done?.invoke(false); return }
        main.postDelayed({
            val view = web
            if (view == null) { done?.invoke(false); return@postDelayed }
            view.evaluateJavascript("window.soundResume ? soundResume() : false") { result ->
                if (result == "true") done?.invoke(true) else resume(tries - 1, done)
            }
        }, 1000)
    }

    fun evaluate(code: String) {
        main.post { web?.evaluateJavascript(code, null) }
    }

    /** Arayüze (app.js aoSet) ses çıkışlarının değiştiğini bildirir. */
    fun pushOutputs(state: JSONObject) {
        if (url == null) return
        pool.execute { runCatching { backend.callAttr("audio_changed", state.toString()) } }
    }

    /** Uygulama açıkken kulaklık takıldı / bağlandı: ayar açıksa ve bir şarkı varsa kaldığı yerden devam. */
    fun onHeadsetAdded() {
        if (!running || !Prefs.headsetPlay(app)) return
        main.postDelayed({ if (loaded && !PlaybackService.isPlaying) resume(3) }, 1500)
    }

    private fun startExternal(intent: Intent) {
        val screen = activity
        runCatching {
            if (screen != null) screen.startActivity(intent)
            else app.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }.onFailure { Log.w(TAG, "Açılamadı: $intent", it) }
    }

    private object Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            if (request.url.host == "127.0.0.1") return false
            startExternal(Intent(Intent.ACTION_VIEW, request.url))  // dış bağlantılar tarayıcıda
            return true
        }

        override fun onPageFinished(view: WebView, url: String) {
            if (view !== web) return
            loaded = true
            activity?.hideSplash()
        }

        override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
            rebuild(view)
            return true
        }
    }

    /** JavaScript'in (SoundNative.call) ve Python'un (android_main) çağırdığı köprü. Ekrana bağlı işler Activity'ye gider. */
    object Native {
        @JavascriptInterface
        fun call(id: Int, method: String, args: String) {
            pool.execute {
                val result = runCatching { backend.callAttr("call", method, args).toString() }
                    .getOrElse { JSONObject().put("error", it.message ?: "Hata").toString() }
                evaluateJs("__soundDone($id,$result)")
            }
        }

        fun evaluateJs(code: String) = evaluate(code)

        fun openUrl(url: String) {
            main.post { startExternal(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
        }

        fun openLogin(url: String) {
            main.post { activity?.showLogin(url) ?: startExternal(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
        }

        fun loginUrl(): String = activity?.loginAddress ?: ""

        fun loginCookies(): String? = CookieManager.getInstance().getCookie("https://music.youtube.com")

        fun closeLogin() {
            main.post { activity?.closeLogin(false) }
        }

        fun clearLogin() {
            CookieManager.getInstance().removeAllCookies(null)
        }

        fun versionCode(): Long = PackageInfoCompat.getLongVersionCode(app.packageManager.getPackageInfo(app.packageName, 0))

        fun versionName(): String = app.packageManager.getPackageInfo(app.packageName, 0).versionName ?: "?"

        fun isMetered(): Boolean = app.getSystemService(ConnectivityManager::class.java).isActiveNetworkMetered

        fun installApk(path: String) {
            main.post { activity?.install(File(path)) ?: Log.w(TAG, "Güncelleme için uygulama açık olmalı") }
        }

        /** Dosya seçici yalnızca uygulama açıkken çalışır; ekransızken boş liste döner. */
        fun pickFiles(multiple: Boolean): String = activity?.pickFiles(multiple) ?: "[]"

        /** Yeni mesaj, arkadaşlık isteği, ortak dinleme daveti. Dokununca uygulama açılır ve hedef gösterilir. */
        fun notify(title: String, body: String, target: String) {
            main.post { SocialNotifier.show(app, title, body, target) }
        }

        fun playerState(json: String) {
            main.post {
                val state = JSONObject(json)
                PlaybackService.update(app, state, web?.url)
                WatchLink.publishState(app, state)
                activity?.onPlayerState(state)
            }
        }

        // ---------- ses çıkışı (app.js aoSection) ----------

        /** Saatteki Kitaplık ekranı için listeler (android_main.watch_lists). */
        fun watchLists(json: String, full: String) = WatchLink.publishLists(app, json, full)

        fun audioOutputs(): String = AudioOutputs.state(app).toString()

        /** Android'de uygulamalar Bluetooth cihazları arasında kendisi geçiş yapamaz: sistemin çıkış seçicisi açılır. */
        fun selectOutput(id: String): String {
            val opened = AudioOutputs.openSwitcher(activity ?: app)
            return (if (opened) JSONObject().put("opened", true) else JSONObject().put("error", "Çıkış seçici açılamadı")).toString()
        }

        fun bluetoothSettings(): Boolean = AudioOutputs.openBluetoothSettings(activity ?: app)

        /** Ayarlar > Çalma'daki kulaklık anahtarları: uygulama kapalıyken de bilinsin diye burada saklanır. */
        fun headsetPrefs(play: Boolean, pause: Boolean) {
            Prefs.setHeadset(app, play, pause)
            if (play) main.post { activity?.askBluetoothPermission() }
        }
    }

    private const val RESUME_TRIES = 30
}

/** Kotlin tarafının da (uygulama kapalıyken) bilmesi gereken ayarlar. */
object Prefs {
    private fun prefs(context: Context) = context.getSharedPreferences("sound", Context.MODE_PRIVATE)
    fun headsetPlay(context: Context) = prefs(context).getBoolean("headset_play", true)
    fun headsetPause(context: Context) = prefs(context).getBoolean("headset_pause", true)
    fun setHeadset(context: Context, play: Boolean, pause: Boolean) {
        prefs(context).edit().putBoolean("headset_play", play).putBoolean("headset_pause", pause).apply()
    }
}
