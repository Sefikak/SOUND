package com.sound.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/** Mesaj, arkadaşlık ve ortak dinleme bildirimleri (çalan şarkı bildiriminden ayrı kanal, sesli). */
object SocialNotifier {
    const val EXTRA_TARGET = "sound_target"
    // Kanalın sesi kanal açılınca sabitlenir; ses değişirse kanal kimliği de değişmeli
    private const val CHANNEL = "social_soft"
    private const val CALL_CHANNEL = "jam_soft"

    fun show(context: Context, title: String, body: String, target: String) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) return
        val manager = context.getSystemService(NotificationManager::class.java)
        // sistemin sert sesi yerine SOUND'un kısa, yumuşak sesi (masaüstündeki web/notify.wav ve ring.wav ile aynı)
        val attributes = AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build()
        fun channel(id: String, name: String, sound: Int) = NotificationChannel(id, name, NotificationManager.IMPORTANCE_HIGH).apply {
            setSound(Uri.parse("android.resource://${context.packageName}/$sound"), attributes)
        }
        listOf("social", "jam").forEach { manager.deleteNotificationChannel(it) }  // eski deneme kanalları (sistem sesiyle)
        manager.createNotificationChannel(channel(CHANNEL, "Mesajlar ve arkadaşlar", R.raw.sound_notify))
        manager.createNotificationChannel(channel(CALL_CHANNEL, "Birlikte dinle davetleri", R.raw.sound_ring))
        val call = target.startsWith("jam:")
        val open = Intent(context, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(EXTRA_TARGET, target)
        // aynı sohbetten gelen bildirimler üst üste biner (aynı kimlik), farklı sohbetler ayrı durur
        val id = target.hashCode()
        val pending = PendingIntent.getActivity(context, id, open, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, if (call) CALL_CHANNEL else CHANNEL)
            .setSmallIcon(R.drawable.ic_note)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setCategory(if (call) NotificationCompat.CATEGORY_CALL else NotificationCompat.CATEGORY_MESSAGE)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(pending)
            .setAutoCancel(true)
            .apply { if (call) setTimeoutAfter(60_000) }  // davet bir dakika sonra kendiliğinden kalkar
            .build()
        runCatching { NotificationManagerCompat.from(context).notify("social", id, notification) }
    }
}
