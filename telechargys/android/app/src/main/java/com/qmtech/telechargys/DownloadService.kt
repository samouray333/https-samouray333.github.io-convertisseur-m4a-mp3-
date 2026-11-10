package com.qmtech.telechargys

import android.app.Notification
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import mobile.Mobile
import org.json.JSONObject

/** Service au premier plan : garde les téléchargements en vie quand l'application est en arrière-plan. */
class DownloadService : Service() {
    companion object {
        @Volatile var running = false
        private const val ID = 1
    }

    private var wake: PowerManager.WakeLock? = null
    private var wifi: WifiManager.WifiLock? = null
    private var idle = 0

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        running = true
        runCatching { Engine.start(this) }
        val type = if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC else 0
        runCatching { ServiceCompat.startForeground(this, ID, build(JSONObject()), type) }.onFailure { stopSelf(); return }
        wake = (getSystemService(POWER_SERVICE) as PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "telechargys:dl").apply { setReferenceCounted(false); acquire(12 * 60 * 60 * 1000L) }
        @Suppress("DEPRECATION")
        wifi = (applicationContext.getSystemService(WIFI_SERVICE) as WifiManager).createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "telechargys:wifi").apply { setReferenceCounted(false); acquire() }
        Engine.main.post(tick)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int) = START_NOT_STICKY

    private val tick = object : Runnable {
        override fun run() {
            if (!running) return
            val s = runCatching { JSONObject(Mobile.summary()) }.getOrDefault(JSONObject())
            if (s.optInt("active") == 0) idle++ else idle = 0
            if (idle >= 4) { stopSelf(); return }
            runCatching { getSystemService(NotificationManager::class.java).notify(ID, build(s)) }
            Engine.main.postDelayed(this, 1000)
        }
    }

    private fun build(s: JSONObject): Notification {
        val active = s.optInt("active")
        val queued = s.optInt("queued")
        val pct = s.optInt("percent", -1)
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getBroadcast(this, 1, Intent(this, ActionReceiver::class.java).setAction("pauseAll"), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val title = if (active == 0) "Telechargys" else "$active téléchargement${if (active > 1) "s" else ""} en cours" + if (queued > 0) " · $queued en attente" else ""
        val text = if (active == 0) "Finalisation…" else Engine.fmtSpeed(s.optLong("speed")) + if (pct >= 0) " · $pct %" else ""
        return NotificationCompat.Builder(this, Engine.CH_PROGRESS)
            .setSmallIcon(R.drawable.ic_stat)
            .setColor(ContextCompat.getColor(this, R.color.accent))
            .setContentTitle(title)
            .setContentText(text)
            .setProgress(100, if (pct >= 0) pct else 0, active > 0 && pct < 0)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(open)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .addAction(0, "Tout arrêter", stop)
            .build()
    }

    // Android 15 limite ce type de service à 6 h par jour : on met proprement en pause.
    override fun onTimeout(startId: Int, fgsType: Int) {
        Thread { runCatching { Mobile.pauseAll(); Mobile.flush() } }.start()
        stopSelf()
    }

    override fun onDestroy() {
        running = false
        Engine.main.removeCallbacks(tick)
        runCatching { wake?.release() }
        runCatching { wifi?.release() }
        Thread { runCatching { Mobile.flush() } }.start()
        super.onDestroy()
    }
}

/** Boutons de la notification. */
class ActionReceiver : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action == "pauseAll") Thread { runCatching { Mobile.pauseAll() } }.start()
    }
}
