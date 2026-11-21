package com.sound.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.ConnectivityManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.OpenableColumns
import android.provider.Settings
import android.view.Gravity
import android.view.View
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
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.addCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.content.pm.PackageInfoCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors

/** Tek ekran: masaüstü SOUND arayüzünü açan WebView. Arka ucu (Python) ve arayüzü birbirine bağlar. */
class MainActivity : ComponentActivity() {
    private lateinit var web: WebView
    private lateinit var splash: View
    private val apiPool = Executors.newCachedThreadPool()
    private val backend: PyObject by lazy { Python.getInstance().getModule("android_main") }
    private var pendingApk: File? = null  // izin ekranından dönünce kurulacak güncelleme
    private lateinit var root: FrameLayout
    private var login: View? = null
    private var loginWeb: WebView? = null
    @Volatile private var loginAddress = ""

    // Dosya seçici (Spotify verisiyle aktarma, çerez dosyası): Python'un iş parçacığı seçim bitene kadar bekler
    @Volatile private var pickWait: CountDownLatch? = null
    @Volatile private var picked: List<Uri> = emptyList()
    private val pickMany = registerForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        picked = uris ?: emptyList(); pickWait?.countDown()
    }
    private val pickOne = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        picked = listOfNotNull(uri); pickWait?.countDown()
    }

    /** Seçilen dosyaları uygulamanın önbelleğine kopyalar (Python content:// okuyamaz), yolları JSON dizisi olarak döner. */
    private fun pickFiles(multiple: Boolean): String {
        val latch = CountDownLatch(1)
        picked = emptyList()
        pickWait = latch
        runOnUiThread {
            runCatching { if (multiple) pickMany.launch(arrayOf("*/*")) else pickOne.launch(arrayOf("*/*")) }
                .onFailure { latch.countDown() }
        }
        latch.await()
        val dir = File(cacheDir, "picked").apply { deleteRecursively(); mkdirs() }
        val paths = JSONArray()
        picked.forEachIndexed { i, uri ->
            runCatching {
                val name = (displayName(uri) ?: "dosya$i").replace(Regex("[\\\\/:*?\"<>|]"), "_")
                val out = File(dir, if (File(dir, name).exists()) "$i-$name" else name)
                contentResolver.openInputStream(uri)?.use { input -> out.outputStream().use { input.copyTo(it) } }
                if (out.exists()) paths.put(out.path)
            }.onFailure { Log.e("SOUND", "Seçilen dosya kopyalanamadı", it) }
        }
        return paths.toString()
    }

    private fun displayName(uri: Uri): String? =
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) it.getString(0) else null
        }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)

        if (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) WebView.setWebContentsDebuggingEnabled(true)

        root = FrameLayout(this).apply { setBackgroundColor(BLACK) }
        web = createWeb()
        root.addView(web, FrameLayout.LayoutParams(-1, -1))
        splash = ImageView(this).apply {
            assets.open("logo.png").use { setImageBitmap(BitmapFactory.decodeStream(it)) }
            setBackgroundColor(BLACK)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            setPadding(180, 0, 180, 0)
        }
        root.addView(splash, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        // Durum ve gezinme çubuklarının altında kalmasın; klavye açılınca da sayfa küçülsün
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.ime())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }

        onBackPressedDispatcher.addCallback(this) {
            loginWeb?.let { page ->
                if (page.canGoBack()) page.goBack() else closeLogin(true)
                return@addCallback
            }
            web.evaluateJavascript("window.soundBack ? soundBack() : false") { handled ->
                if (handled != "true") moveTaskToBack(true)  // uygulama kapanmasın, müzik sürsün
            }
        }
        askNotificationPermission()
        val data = filesDir.resolve("sound").absolutePath
        apiPool.execute {
            val url = backend.callAttr("start", data, Native()).toString()
            runOnUiThread { web.loadUrl(url) }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun createWeb() = WebView(this).apply {
        setBackgroundColor(BLACK)
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.mediaPlaybackRequiresUserGesture = false  // sıradaki şarkıya kendiliğinden geçebilsin
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        settings.allowFileAccess = false
        setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false)  // ekran kapalıyken de müzik sürsün
        overScrollMode = View.OVER_SCROLL_NEVER
        addJavascriptInterface(Native(), "SoundNative")
        webViewClient = Client()
        webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(m: ConsoleMessage): Boolean {
                Log.i("SOUNDjs", "${m.message()} @${m.lineNumber()}")
                return true
            }
        }
    }

    /** Arayüz süreci öldü (çoğunlukla bellek yetmedi): yalnızca WebView yenilenir, çalıyorsa şarkı kaldığı yerden sürer. */
    private fun rebuildWeb(dead: WebView) {
        if (dead !== web) return
        val url = dead.url
        val resume = PlaybackService.isPlaying
        root.removeView(dead)
        dead.destroy()
        web = createWeb()
        root.addView(web, 0, FrameLayout.LayoutParams(-1, -1))
        if (url != null) web.loadUrl(url)
        if (resume) resumePlayback(RESUME_TRIES)
    }

    /** Sayfa ve oturum yüklenene kadar saniyede bir dener. */
    private fun resumePlayback(tries: Int) {
        if (tries <= 0 || isDestroyed) return
        web.postDelayed({
            web.evaluateJavascript("window.soundResume ? soundResume() : false") { done ->
                if (done != "true") resumePlayback(tries - 1)
            }
        }, 1000)
    }

    /** Samsung gibi telefonlar pil tasarrufu için arka plandaki uygulamayı kapatabilir: ilk çalmada bir kez izin istenir. */
    @SuppressLint("BatteryLife")
    private fun askBatteryExemption() {
        val prefs = getSharedPreferences("sound", MODE_PRIVATE)
        if (prefs.getBoolean("battery_asked", false)) return
        if (getSystemService(PowerManager::class.java).isIgnoringBatteryOptimizations(packageName)) return
        prefs.edit().putBoolean("battery_asked", true).apply()
        runCatching {
            startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
        }.onFailure { Log.w("SOUND", "Pil izni ekranı açılamadı", it) }
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    /** Çalma durumu kaydedilsin; WebView bilerek duraklatılmıyor, müzik arka planda sürer. */
    override fun onStop() {
        super.onStop()
        web.evaluateJavascript("window.soundSave && soundSave()", null)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        openTarget(intent)
    }

    /** Bildirimden gelindi: arayüz hazır olunca sohbet / davet açılır. */
    private fun openTarget(intent: Intent?) {
        val target = intent?.getStringExtra(SocialNotifier.EXTRA_TARGET) ?: return
        intent.removeExtra(SocialNotifier.EXTRA_TARGET)
        apiPool.execute { runCatching { backend.callAttr("open_target", target) } }
    }

    override fun onResume() {
        super.onResume()
        pendingApk?.let { apk ->
            pendingApk = null
            if (packageManager.canRequestPackageInstalls()) install(apk)
        }
    }

    /** Sistemin yükleme ekranını açar. Bilinmeyen kaynak izni ilk seferde kullanıcıdan istenir. */
    private fun install(apk: File) {
        if (!packageManager.canRequestPackageInstalls()) {
            pendingApk = apk
            startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
            return
        }
        val uri = FileProvider.getUriForFile(this, "$packageName.files", apk)
        startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
    }

    /** Google girişi: ayrı bir WebView. Yalnızca oturum çerezleri okunur, parola uygulamaya hiç gelmez. */
    @SuppressLint("SetJavaScriptEnabled")
    private fun showLogin(url: String) {
        closeLogin(false)
        val page = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = object : WebViewClient() {
                override fun doUpdateVisitedHistory(view: WebView, address: String, isReload: Boolean) {
                    loginAddress = address
                }

                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) =
                    request.url.scheme != "https"

                override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                    closeLogin(true)  // işlenmezse Android tüm uygulamayı kapatır
                    return true
                }
            }
        }
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(page, true)
        }
        val close = TextView(this).apply {
            text = "Kapat"
            textSize = 16f
            setTextColor(WHITE)
            gravity = Gravity.CENTER
            setPadding(48, 36, 48, 36)
            setOnClickListener { closeLogin(true) }
        }
        val screen = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(BLACK)
            isClickable = true
            addView(close, LinearLayout.LayoutParams(-2, -2).apply { gravity = Gravity.END })
            addView(page, LinearLayout.LayoutParams(-1, 0, 1f))
        }
        root.addView(screen, FrameLayout.LayoutParams(-1, -1))
        login = screen
        loginWeb = page
        page.loadUrl(url)
    }

    private fun closeLogin(notify: Boolean) {
        val screen = login ?: return
        root.removeView(screen)
        loginWeb?.destroy()
        login = null
        loginWeb = null
        loginAddress = ""
        if (notify) apiPool.execute { runCatching { backend.callAttr("login_closed") } }
    }

    override fun onDestroy() {
        stopService(Intent(this, PlaybackService::class.java))
        web.destroy()
        super.onDestroy()
    }

    private inner class Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            if (request.url.host == "127.0.0.1") return false
            runCatching { startActivity(Intent(Intent.ACTION_VIEW, request.url)) }  // dış bağlantılar tarayıcıda
            return true
        }

        override fun onPageFinished(view: WebView, url: String) {
            splash.visibility = View.GONE
        }

        override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
            rebuildWeb(view)
            return true
        }
    }

    /** JavaScript ve Python'un çağırdığı köprü. */
    inner class Native {
        @JavascriptInterface
        fun call(id: Int, method: String, args: String) {
            apiPool.execute {
                val result = runCatching { backend.callAttr("call", method, args).toString() }
                    .getOrElse { JSONObject().put("error", it.message ?: "Hata").toString() }
                evaluateJs("__soundDone($id,$result)")
            }
        }

        fun openUrl(url: String) {
            runOnUiThread { runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) } }
        }

        fun openLogin(url: String) {
            runOnUiThread { showLogin(url) }
        }

        fun loginUrl(): String = loginAddress

        fun loginCookies(): String? = CookieManager.getInstance().getCookie("https://music.youtube.com")

        fun closeLogin() {
            runOnUiThread { this@MainActivity.closeLogin(false) }
        }

        fun clearLogin() {
            CookieManager.getInstance().removeAllCookies(null)
        }

        fun evaluateJs(code: String) {
            runOnUiThread { if (!isDestroyed) web.evaluateJavascript(code, null) }
        }

        fun versionCode(): Long = PackageInfoCompat.getLongVersionCode(packageManager.getPackageInfo(packageName, 0))

        fun versionName(): String = packageManager.getPackageInfo(packageName, 0).versionName ?: "?"

        fun isMetered(): Boolean = getSystemService(ConnectivityManager::class.java).isActiveNetworkMetered

        fun installApk(path: String) {
            runOnUiThread { runCatching { install(File(path)) }.onFailure { Log.e("SOUND", "Güncelleme açılamadı", it) } }
        }

        fun pickFiles(multiple: Boolean): String = this@MainActivity.pickFiles(multiple)

        /** Yeni mesaj, arkadaşlık isteği, ortak dinleme daveti. Dokununca uygulama açılır ve hedef gösterilir. */
        fun notify(title: String, body: String, target: String) {
            runOnUiThread { SocialNotifier.show(this@MainActivity, title, body, target) }
        }

        fun playerState(json: String) {
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                val state = JSONObject(json)
                PlaybackService.update(this@MainActivity, state, web.url)
                if (state.optBoolean("playing") && hasWindowFocus()) askBatteryExemption()
            }
        }
    }

    private companion object {
        const val BLACK = 0xFF000000.toInt()
        const val WHITE = 0xFFFFFFFF.toInt()
        const val RESUME_TRIES = 30
    }
}
