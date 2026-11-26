package com.sound.wear

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.Handler
import android.os.Looper
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.util.concurrent.Executors

/** Saattaki Python (watch_main.py): şarkıyı bulma, indirme, akıllı sıra, arama. Çağrılar engelleyicidir, arka planda yapılır. */
object Py {
    val pool = Executors.newFixedThreadPool(3)
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var started = false

    /** Python'u başlat (ilk seferde ~1-2 sn). Herhangi bir iş parçacığından çağrılabilir; ikinci çağrı hemen döner. */
    fun start(context: Context) {
        if (started) return
        synchronized(this) {
            if (started) return
            val app = context.applicationContext
            if (!Python.isStarted()) Python.start(AndroidPlatform(app))
            Python.getInstance().getModule("watch_main").callAttr("start", app.filesDir.resolve("sound").absolutePath)
            started = true
        }
    }

    /** Engelleyici çağrı: sonuç JSON nesnesi ({"error": ...} olabilir). */
    fun call(context: Context, name: String, vararg args: Any): JSONObject = runCatching {
        start(context)
        val out = Python.getInstance().getModule("watch_main").callAttr(name, *args)?.toString()
        if (out.isNullOrEmpty() || out == "None") JSONObject() else JSONObject(out)
    }.getOrElse {
        Log.w("SOUND", "Python $name", it)
        JSONObject().put("error", it.message ?: "Hata")
    }

    fun raw(context: Context, name: String, vararg args: Any): String? = runCatching {
        start(context)
        Python.getInstance().getModule("watch_main").callAttr(name, *args)?.toString()
    }.getOrNull()

    /** Arka planda çağır, sonucu ana iş parçacığında ver. */
    fun async(context: Context, name: String, vararg args: Any, done: (JSONObject) -> Unit) {
        val app = context.applicationContext
        pool.execute {
            val result = call(app, name, *args)
            main.post { done(result) }
        }
    }

    fun warm(context: Context) {
        val app = context.applicationContext
        if (!started) pool.execute { runCatching { start(app) } }
    }
}

/**
 * Saatin interneti. Telefon yanındayken Wear OS interneti Bluetooth üzerinden telefondan verir (yavaş), Wi-Fi kapalıdır.
 * Şarkı indirirken Wi-Fi istenir ve bu süreç ona bağlanır; iş bitince bırakılır (pil). Wi-Fi yoksa var olan bağlantı kullanılır.
 */
object Net {
    private var users = 0
    private var callback: ConnectivityManager.NetworkCallback? = null

    @Synchronized fun acquire(context: Context) {
        users++
        if (callback != null) return
        val cm = context.applicationContext.getSystemService(ConnectivityManager::class.java)
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { cm.bindProcessToNetwork(network) }
            override fun onLost(network: Network) { if (cm.boundNetworkForProcess == network) cm.bindProcessToNetwork(null) }
        }
        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .build()
        runCatching { cm.requestNetwork(request, cb); callback = cb }
            .onFailure { Log.w("SOUND", "Wi-Fi istenemedi", it) }
    }

    @Synchronized fun release(context: Context) {
        if (users > 0) users--
        if (users > 0) return
        val cm = context.applicationContext.getSystemService(ConnectivityManager::class.java)
        callback?.let { runCatching { cm.unregisterNetworkCallback(it) } }
        callback = null
        cm.bindProcessToNetwork(null)
    }

    fun online(context: Context): Boolean {
        val cm = context.applicationContext.getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.boundNetworkForProcess ?: cm.activeNetwork) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
}
