package com.sound.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.OpenableColumns
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.View
import android.webkit.CookieManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.addCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import com.chaquo.python.Python
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.CountDownLatch

/**
 * Tek ekran: çalma motorunun (Engine: WebView + Python) arayüzünü gösterir. Motor ekrandan bağımsızdır; ekran kapanınca
 * müzik sürer, uygulama kapalıyken kulaklık bağlanınca motor ekransız da başlayabilir.
 */
class MainActivity : ComponentActivity() {
    private lateinit var splash: View
    private var pendingApk: File? = null  // izin ekranından dönünce kurulacak güncelleme
    private lateinit var root: FrameLayout
    private var login: View? = null
    private var loginWeb: WebView? = null
    @Volatile var loginAddress = ""
        private set

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
    fun pickFiles(multiple: Boolean): String {
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        Python.getInstance()  // PyApplication başlattı; motor ilk kez burada da başlayabilir

        root = FrameLayout(this).apply { setBackgroundColor(BLACK) }
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
            val web = Engine.web
            if (web == null) {
                moveTaskToBack(true)
                return@addCallback
            }
            web.evaluateJavascript("window.soundBack ? soundBack() : false") { handled ->
                if (handled != "true") moveTaskToBack(true)  // uygulama kapanmasın, müzik sürsün
            }
        }
        askNotificationPermission()
        Engine.start(this)
        Engine.attach(this, root)
        openTarget(intent)
    }

    fun hideSplash() {
        splash.visibility = View.GONE
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

    fun onPlayerState(state: JSONObject) {
        if (!state.optBoolean("playing") || !hasWindowFocus()) return
        askBatteryExemption()
        askBluetoothPermission()
    }

    /**
     * Uygulama kapalıyken Bluetooth kulaklığın bağlandığını duyabilmek için Android 12+ "Yakındaki cihazlar" izni gerekir.
     * "Kulaklık bağlanınca çal" açıksa bir kez sorulur; verilmezse kulaklık yalnızca uygulama açıkken algılanır.
     */
    fun askBluetoothPermission() {
        if (Build.VERSION.SDK_INT < 31 || !Prefs.headsetPlay(this)) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED) return
        val prefs = getSharedPreferences("sound", MODE_PRIVATE)
        if (prefs.getBoolean("bluetooth_asked", false)) return
        prefs.edit().putBoolean("bluetooth_asked", true).apply()
        requestPermissions(arrayOf(Manifest.permission.BLUETOOTH_CONNECT), 2)
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)
    }

    /** Çalma durumu kaydedilsin; WebView bilerek duraklatılmıyor, müzik arka planda sürer. */
    override fun onStop() {
        super.onStop()
        Engine.evaluate("window.soundSave && soundSave()")
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
        Engine.pool.execute { runCatching { Python.getInstance().getModule("android_main").callAttr("open_target", target) } }
    }

    override fun onResume() {
        super.onResume()
        pendingApk?.let { apk ->
            pendingApk = null
            if (packageManager.canRequestPackageInstalls()) install(apk)
        }
    }

    /** Sistemin yükleme ekranını açar. Bilinmeyen kaynak izni ilk seferde kullanıcıdan istenir. */
    fun install(apk: File) {
        runCatching {
            if (!packageManager.canRequestPackageInstalls()) {
                pendingApk = apk
                startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
                return
            }
            val uri = FileProvider.getUriForFile(this, "$packageName.files", apk)
            startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
        }.onFailure { Log.e("SOUND", "Güncelleme açılamadı", it) }
    }

    /** Google girişi: ayrı bir WebView. Yalnızca oturum çerezleri okunur, parola uygulamaya hiç gelmez. */
    @SuppressLint("SetJavaScriptEnabled")
    fun showLogin(url: String) {
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

    fun closeLogin(notify: Boolean) {
        val screen = login ?: return
        root.removeView(screen)
        loginWeb?.destroy()
        login = null
        loginWeb = null
        loginAddress = ""
        if (notify) Engine.pool.execute { runCatching { Python.getInstance().getModule("android_main").callAttr("login_closed") } }
    }

    override fun onDestroy() {
        closeLogin(false)
        Engine.detach(this)
        // ekran kapandı ama müzik çalıyorsa motor ekransız sürer; çalmıyorsa her şey kapanır (eski davranış)
        if (!isChangingConfigurations && !PlaybackService.isPlaying) {
            Engine.shutdown()
            stopService(Intent(this, PlaybackService::class.java))
        }
        super.onDestroy()
    }

    private companion object {
        const val BLACK = 0xFF000000.toInt()
        const val WHITE = 0xFFFFFFFF.toInt()
    }
}
