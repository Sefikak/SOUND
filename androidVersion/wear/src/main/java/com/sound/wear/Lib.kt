package com.sound.wear

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Çalma yeri: "phone" (Bluetooth'la bağlı telefondaki SOUND'u kumanda), "watch" (saatin kendisi) ya da "dev:<kimlik>"
 * (hesaptaki başka bir SOUND, ör. PC; internet üzerinden). Şimdi Çalıyor ekranının üstündeki düğmeyle seçilir.
 */
object Where {
    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences("sound", Context.MODE_PRIVATE)
    fun get(context: Context): String = prefs(context).getString("where", "phone") ?: "phone"
    fun watch(context: Context) = get(context) == "watch"
    fun phone(context: Context) = get(context) == "phone"
    /** Hesaptaki cihazı kumanda ediyorsak onun kimliği. */
    fun device(context: Context): String? = get(context).takeIf { it.startsWith("dev:") }?.removePrefix("dev:")
    fun set(context: Context, where: String) = prefs(context).edit().putString("where", where).apply()
}

/**
 * Telefonun gönderdiği kitaplık (favoriler, albümler, mixler, son çalınanlar ve şarkıları). Saatte dosyada saklanır:
 * telefon uzaktayken saat bunlardan çalar. Saatte yapılan beğeniler telefona ulaşana kadar burada bekler.
 */
object Lib {
    @Volatile private var data: JSONObject? = null
    private const val FILE = "library.json"

    fun get(context: Context): JSONObject? {
        data?.let { return it }
        val file = context.applicationContext.filesDir.resolve(FILE)
        data = runCatching { JSONObject(file.readText()) }.getOrNull()
        return data
    }

    fun save(context: Context, json: JSONObject) {
        data = json
        runCatching {
            val file = context.applicationContext.filesDir.resolve(FILE)
            val temp = file.resolveSibling("$FILE.part")
            temp.writeText(json.toString())
            temp.renameTo(file)
        }
        // telefonun kitaplığı bu beğenileri artık içeriyorsa yereldeki geçersizleşir
        val prefs = prefs(context)
        val overrides = runCatching { JSONObject(prefs.getString("likes", "{}")!!) }.getOrDefault(JSONObject())
        val pending = pendingIds(context)
        val keys = overrides.keys().asSequence().toList()
        for (id in keys) if (id !in pending && favoriteIds(json).contains(id) == overrides.optBoolean(id)) overrides.remove(id)
        prefs.edit().putString("likes", overrides.toString()).apply()
    }

    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences("sound", Context.MODE_PRIVATE)

    private fun favoriteIds(json: JSONObject?): Set<String> {
        val favs = json?.optJSONArray("favorites") ?: return emptySet()
        return (0 until favs.length()).map { favs.getJSONObject(it).optString("id") }.toSet()
    }

    fun isLiked(context: Context, id: String): Boolean {
        val overrides = runCatching { JSONObject(prefs(context).getString("likes", "{}")!!) }.getOrDefault(JSONObject())
        if (overrides.has(id)) return overrides.optBoolean(id)
        return favoriteIds(get(context)).contains(id)
    }

    /** Saatte beğen / beğeniyi kaldır. Telefona hemen gönderilir; telefon yoksa bağlanınca gönderilir. */
    fun setLiked(context: Context, track: JSONObject, on: Boolean) {
        val prefs = prefs(context)
        val overrides = runCatching { JSONObject(prefs.getString("likes", "{}")!!) }.getOrDefault(JSONObject())
        overrides.put(track.optString("id"), on)
        val pending = runCatching { JSONArray(prefs.getString("pending_likes", "[]")) }.getOrDefault(JSONArray())
        pending.put(JSONObject().put("track", slim(track)).put("on", on))
        prefs.edit().putString("likes", overrides.toString()).putString("pending_likes", pending.toString()).apply()
        Link.flushLikes(context)
    }

    /** "Beğenmedim": telefona gider (oradan hesaba); saatte o şarkı geçilir. */
    fun dislike(context: Context, track: JSONObject) {
        val prefs = prefs(context)
        val pending = runCatching { JSONArray(prefs.getString("pending_likes", "[]")) }.getOrDefault(JSONArray())
        pending.put(JSONObject().put("track", slim(track)).put("on", true).put("dislike", true))
        prefs.edit().putString("pending_likes", pending.toString()).apply()
        Link.flushLikes(context)
    }

    private fun pendingIds(context: Context): Set<String> {
        val pending = runCatching { JSONArray(prefs(context).getString("pending_likes", "[]")) }.getOrDefault(JSONArray())
        return (0 until pending.length()).map { pending.getJSONObject(it).optJSONObject("track")?.optString("id") ?: "" }.toSet()
    }

    /** Gönderilmeyi bekleyen beğeniler: Link bunları telefona yollar, başarılı olanları siler. */
    @Synchronized fun takePending(context: Context): JSONArray {
        val prefs = prefs(context)
        val pending = runCatching { JSONArray(prefs.getString("pending_likes", "[]")) }.getOrDefault(JSONArray())
        prefs.edit().putString("pending_likes", "[]").apply()
        return pending
    }

    @Synchronized fun putBack(context: Context, items: List<JSONObject>) {
        if (items.isEmpty()) return
        val prefs = prefs(context)
        val pending = runCatching { JSONArray(prefs.getString("pending_likes", "[]")) }.getOrDefault(JSONArray())
        items.forEach { pending.put(it) }
        prefs.edit().putString("pending_likes", pending.toString()).apply()
    }

    fun slim(track: JSONObject): JSONObject = JSONObject()
        .put("id", track.optString("id"))
        .put("title", track.optString("title"))
        .put("artist", track.optString("artist"))
        .put("duration", track.optInt("duration", track.optDouble("dur", 0.0).toInt()))

    /** Bir listenin şarkıları: kind favorites | album (id) | mix (key) | recent | offline (key). */
    fun tracks(context: Context, kind: String, key: String = ""): JSONArray {
        val lib = get(context) ?: JSONObject()
        return when (kind) {
            "favorites" -> lib.optJSONArray("favorites") ?: JSONArray()
            "recent" -> lib.optJSONArray("recent") ?: JSONArray()
            "album" -> find(lib.optJSONArray("albums"), "id", key)?.optJSONArray("tracks") ?: JSONArray()
            "mix" -> find(lib.optJSONArray("mixes"), "key", key)?.optJSONArray("tracks") ?: JSONArray()
            "offline" -> Offline.list(context, key)?.optJSONArray("tracks") ?: JSONArray()
            else -> JSONArray()
        }
    }

    private fun find(items: JSONArray?, field: String, value: String): JSONObject? {
        if (items == null) return null
        for (i in 0 until items.length()) if (items.getJSONObject(i).optString(field) == value) return items.getJSONObject(i)
        return null
    }
}
