package com.qmtech.telechargys

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.Looper
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import mobile.Mobile
import org.json.JSONObject
import java.io.File

/** Moteur de téléchargement (bibliothèque Go) : un seul exemplaire pour toute l'application. */
object Engine {
    const val CH_PROGRESS = "progression"
    const val CH_DONE = "termines"

    lateinit var app: Context
        private set
    var port = 0
        private set
    var token = ""
        private set
    val baseUrl get() = "http://127.0.0.1:$port"
    val ready get() = port != 0
    val main = Handler(Looper.getMainLooper())

    private var wifiOnly = false
    private var notifyDone = true
    private var doneId = 1000

    val downloadDir: File
        get() = File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Telechargys")

    @Synchronized
    fun start(ctx: Context) {
        if (ready) return
        app = ctx.applicationContext
        channels()
        runCatching { Mobile.setTimeZone(java.util.TimeZone.getDefault().id) }
        val res = Mobile.start(File(app.filesDir, "moteur").absolutePath, downloadDir.absolutePath, object : mobile.Callback {
            override fun onEvent(kind: String, data: String) {
                main.post { runCatching { onEvent(kind, JSONObject(data)) } }
            }
        })
        val parts = res.split("|")
        token = parts[1]
        port = parts[0].toInt()
        readSettings(JSONObject(Mobile.settings()))
        watchNetwork()
        main.post(ticker)
    }

    private fun channels() {
        if (Build.VERSION.SDK_INT < 26) return
        val nm = app.getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_PROGRESS, "Téléchargements en cours", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) })
        nm.createNotificationChannel(NotificationChannel(CH_DONE, "Téléchargements terminés", NotificationManager.IMPORTANCE_DEFAULT))
    }

    private fun readSettings(s: JSONObject) {
        wifiOnly = s.optBoolean("wifiOnly", false)
        notifyDone = s.optBoolean("notifyDone", true)
        checkNetwork()
    }

    private fun onEvent(kind: String, d: JSONObject) {
        when (kind) {
            "settings" -> readSettings(d)
            "notify" -> if (notifyDone) notifyResult(d)
        }
    }

    private fun notifyResult(d: JSONObject) {
        val done = d.optString("kind") == "done"
        val path = d.optString("path")
        val intent = (if (done && path.isNotEmpty()) Files.viewIntent(app, path) else null)
            ?: Intent(app, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        val pi = PendingIntent.getActivity(app, doneId, intent, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val n = NotificationCompat.Builder(app, CH_DONE)
            .setSmallIcon(R.drawable.ic_stat)
            .setColor(ContextCompat.getColor(app, R.color.accent))
            .setContentTitle(d.optString("title"))
            .setContentText(d.optString("body"))
            .setStyle(NotificationCompat.BigTextStyle().bigText(d.optString("body")))
            .setAutoCancel(true)
            .setContentIntent(pi)
            .build()
        runCatching { app.getSystemService(NotificationManager::class.java).notify(doneId++, n) }
    }

    // ----- réseau : option « Wi-Fi uniquement » -----
    private fun watchNetwork() {
        val cm = app.getSystemService(ConnectivityManager::class.java)
        runCatching {
            cm.registerDefaultNetworkCallback(object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) = main.post { checkNetwork() }.let { }
                override fun onLost(network: Network) = main.post { checkNetwork() }.let { }
                override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) = main.post { checkNetwork() }.let { }
            })
        }
    }

    private fun checkNetwork() {
        if (!ready) return
        val cm = app.getSystemService(ConnectivityManager::class.java)
        val caps = cm.getNetworkCapabilities(cm.activeNetwork)
        val wifi = caps != null && (caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) || caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET))
        val blocked = wifiOnly && !wifi
        Thread { Mobile.setBlocked(blocked) }.start()
    }

    // ----- surveillance : lance le service au premier plan dès qu'un téléchargement tourne -----
    private val ticker = object : Runnable {
        override fun run() {
            runCatching {
                val s = JSONObject(Mobile.summary())
                if (s.optInt("active") > 0 && !DownloadService.running) {
                    ContextCompat.startForegroundService(app, Intent(app, DownloadService::class.java))
                }
            }
            main.postDelayed(this, 1500)
        }
    }

    fun fmtSpeed(n: Long): String {
        var v = n.toDouble()
        val u = arrayOf("o", "Ko", "Mo", "Go")
        var i = 0
        while (v >= 1024 && i < 3) { v /= 1024; i++ }
        return (if (i == 0) v.toInt().toString() else String.format(java.util.Locale.FRANCE, "%.1f", v)) + " " + u[i] + "/s"
    }
}
