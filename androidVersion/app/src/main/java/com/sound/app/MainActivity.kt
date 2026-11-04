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
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.content.pm.PackageInfoCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import org.json.JSONObject
import java.io.File
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

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)

        if (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) WebView.setWebContentsDebuggingEnabled(true)

        root = FrameLayout(this).apply { setBackgroundColor(BLACK) }
        web = WebView(this).apply {
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
        if (notify) apiPool.execute { backend.callAttr("login_closed") }
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
            recreate()  // arayüz süreci öldüyse uygulama düşmesin, baştan aç
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

        fun playerState(json: String) {
            runOnUiThread { PlaybackService.update(this@MainActivity, JSONObject(json), web.url) }
        }
    }

    private companion object {
        const val BLACK = 0xFF000000.toInt()
        const val WHITE = 0xFFFFFFFF.toInt()
    }
}
