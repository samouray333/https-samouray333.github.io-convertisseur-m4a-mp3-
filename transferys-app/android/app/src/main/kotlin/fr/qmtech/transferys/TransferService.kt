package fr.qmtech.transferys

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat

/**
 * Service au premier plan :
 *  - pendant les transferts (notification de progression + verrous processeur
 *    et Wi-Fi) pour que tout continue écran éteint ;
 *  - tant que « Accès à distance » est activé, pour rester joignable par le PC.
 */
class TransferService : Service() {
    companion object {
        const val ACTION_UPDATE = "fr.qmtech.transferys.UPDATE"
        const val ACTION_STOP = "fr.qmtech.transferys.STOP"
        const val ACTION_REMOTE_ON = "fr.qmtech.transferys.REMOTE_ON"
        const val ACTION_REMOTE_OFF = "fr.qmtech.transferys.REMOTE_OFF"
        const val CHANNEL = "transferys_progress"
        const val NOTIF_ID = 7301
        @Volatile var running = false
    }

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var remote = false
    private var transfer = false
    private var title = "Transfert en cours"
    private var text = ""
    private var percent = -1

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> transfer = false
            ACTION_REMOTE_ON -> remote = true
            ACTION_REMOTE_OFF -> remote = false
            else -> {
                transfer = true
                title = intent?.getStringExtra("title") ?: "Transfert en cours"
                text = intent?.getStringExtra("text") ?: ""
                percent = intent?.getIntExtra("percent", -1) ?: -1
            }
        }
        if (!remote && !transfer) {
            stopEverything()
            return START_NOT_STICKY
        }
        val n = build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            var type = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            if (remote) type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            startForeground(NOTIF_ID, n, type)
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, n)
        }
        running = true
        if (transfer) acquireLocks() else releaseLocks()
        return if (remote) START_STICKY else START_NOT_STICKY
    }

    private fun build(): Notification {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "Transferts et accès à distance", NotificationManager.IMPORTANCE_LOW).apply {
                    description = "Progression des transferts, accès à distance actif"
                    setShowBadge(false)
                }
            )
        }
        val open = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val b = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_transferys)
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setContentIntent(open)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
        if (transfer) {
            b.setContentTitle(title).setContentText(text)
                .setCategory(NotificationCompat.CATEGORY_PROGRESS)
                .setProgress(100, percent.coerceIn(0, 100), percent < 0)
        } else {
            b.setContentTitle("Accès à distance actif")
                .setContentText("Votre PC peut joindre ce téléphone (dossiers partagés, envois).")
                .setCategory(NotificationCompat.CATEGORY_SERVICE)
        }
        return b.build()
    }

    private fun acquireLocks() {
        if (wakeLock != null) return
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "Transferys:transfer").apply {
                setReferenceCounted(false)
                acquire(6 * 60 * 60 * 1000L)
            }
            val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            @Suppress("DEPRECATION")
            wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "Transferys:wifi").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (_: Exception) {}
    }

    private fun releaseLocks() {
        try { wakeLock?.release() } catch (_: Exception) {}
        try { wifiLock?.release() } catch (_: Exception) {}
        wakeLock = null
        wifiLock = null
    }

    private fun stopEverything() {
        releaseLocks()
        running = false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) stopForeground(STOP_FOREGROUND_REMOVE) else @Suppress("DEPRECATION") stopForeground(true)
        stopSelf()
    }

    /** Android 15 : limite de durée des services « dataSync ». */
    override fun onTimeout(startId: Int, fgsType: Int) {
        if (remote) {
            transfer = false
            releaseLocks()
        } else {
            stopEverything()
        }
    }

    override fun onDestroy() {
        releaseLocks()
        running = false
        super.onDestroy()
    }
}
