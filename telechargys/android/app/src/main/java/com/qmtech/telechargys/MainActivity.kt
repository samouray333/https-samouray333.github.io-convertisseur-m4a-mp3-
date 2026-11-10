package com.qmtech.telechargys

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.webkit.JavascriptInterface
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import mobile.Mobile
import org.json.JSONObject
import java.io.File

/** Écran principal : affiche l'interface servie par le moteur local. */
class MainActivity : Activity() {
    private lateinit var web: WebView
    private var pageReady = false
    private val pending = ArrayList<String>()
    private var fileCb: ValueCallback<Array<Uri>>? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val root = FrameLayout(this)
        root.setBackgroundColor(ContextCompat.getColor(this, R.color.bar))
        web = WebView(this)
        root.addView(web, ViewGroup.LayoutParams(-1, -1))
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            WindowInsetsCompat.CONSUMED
        }
        applyBars()

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            textZoom = 100
            setSupportZoom(false)
        }
        web.setBackgroundColor(ContextCompat.getColor(this, R.color.bar))
        web.overScrollMode = WebView.OVER_SCROLL_NEVER
        web.addJavascriptInterface(Bridge(), "TYAndroid")
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val u = request.url.toString()
                if (u.startsWith(Engine.baseUrl)) return false
                runCatching { startActivity(Intent(Intent.ACTION_VIEW, request.url)) }
                return true
            }
            override fun onPageFinished(view: WebView, url: String) {
                pushTheme()
                web.postDelayed({ pageReady = true; flush() }, 700)
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(view: WebView, cb: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
                fileCb?.onReceiveValue(null)
                fileCb = cb
                return runCatching {
                    startActivityForResult(Intent(Intent.ACTION_GET_CONTENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*"), 7)
                    true
                }.getOrElse { fileCb = null; false }
            }
        }

        askPermissions()
        handleIntent(intent)
        Thread {
            val err = runCatching { Engine.start(this) }.exceptionOrNull()
            runOnUiThread {
                if (err != null) web.loadData("<p style='font:16px sans-serif;padding:24px'>Impossible de démarrer le moteur de téléchargement : ${err.message}</p>", "text/html; charset=utf-8", "utf-8")
                else web.loadUrl(Engine.baseUrl + "/?token=" + Engine.token)
            }
        }.start()
    }

    private fun night() = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES

    private fun applyBars() {
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = !night()
            isAppearanceLightNavigationBars = !night()
        }
    }

    private fun pushTheme() = web.evaluateJavascript("window.tySystemDark=${night()};window.applyTheme&&applyTheme();", null)

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        applyBars()
        pushTheme()
    }

    private fun askPermissions() {
        val need = ArrayList<String>()
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) need += Manifest.permission.POST_NOTIFICATIONS
        if (Build.VERSION.SDK_INT <= 29 && checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) need += Manifest.permission.WRITE_EXTERNAL_STORAGE
        if (need.isNotEmpty()) requestPermissions(need.toTypedArray(), 1)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntent(intent)
    }

    private val urlRe = Regex("""(https?|ftp)://[^\s<>"']+""", RegexOption.IGNORE_CASE)

    private fun handleIntent(intent: Intent?) {
        intent ?: return
        val text = when (intent.action) {
            Intent.ACTION_SEND -> intent.getStringExtra(Intent.EXTRA_TEXT)
            Intent.ACTION_VIEW -> intent.dataString
            else -> null
        } ?: return
        val urls = urlRe.findAll(text).map { it.value.trimEnd('.', ',', ')', ';') }.distinct().toList()
        if (urls.isEmpty()) return
        pending += urls
        flush()
        intent.action = Intent.ACTION_MAIN // ne pas rejouer le lien à la rotation
    }

    /** Envoie les liens reçus une fois l'interface prête (elle affiche la fenêtre « Nouveau téléchargement »). */
    private fun flush() {
        if (!pageReady || !Engine.ready) return
        val list = ArrayList(pending)
        pending.clear()
        if (list.isEmpty()) return
        val arr = org.json.JSONArray(list).toString()
        web.evaluateJavascript("window.tyAddUrls&&tyAddUrls($arr);", null)
    }

    @Deprecated("API simple suffisante ici")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode == 7) {
            fileCb?.onReceiveValue(if (resultCode == RESULT_OK && data?.data != null) arrayOf(data.data!!) else null)
            fileCb = null
        }
    }

    @Deprecated("Retour : ferme d'abord la fenêtre ouverte dans l'interface")
    override fun onBackPressed() {
        web.evaluateJavascript("(window.tyBack&&window.tyBack())||false") { r ->
            if (r != "true") moveTaskToBack(true)
        }
    }

    override fun onPause() {
        super.onPause()
        if (Engine.ready) Thread { runCatching { Mobile.flush() } }.start()
    }

    /** Fonctions appelées par l'interface web. */
    inner class Bridge {
        @JavascriptInterface fun openFile(path: String) = runOnUiThread { Files.open(this@MainActivity, path) }
        @JavascriptInterface fun openFolder(path: String) = runOnUiThread { Files.openDownloads(this@MainActivity) }
        @JavascriptInterface fun share(path: String) = runOnUiThread { Files.share(this@MainActivity, path) }
        @JavascriptInterface fun openBrowser(url: String) = runOnUiThread {
            startActivity(Intent(this@MainActivity, BrowserActivity::class.java).putExtra("url", url))
        }
        @JavascriptInterface fun getClipboard(): String = runCatching {
            val cm = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
            cm.primaryClip?.getItemAt(0)?.coerceToText(this@MainActivity)?.toString() ?: ""
        }.getOrDefault("")
        @JavascriptInterface fun copy(text: String) {
            runCatching { (getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("Telechargys", text)) }
        }
        @JavascriptInterface fun saveText(name: String, content: String): String {
            val dir = Engine.downloadDir.apply { mkdirs() }
            var f = File(dir, name)
            var i = 1
            while (f.exists()) { f = File(dir, name.substringBeforeLast('.') + " ($i)." + name.substringAfterLast('.')); i++ }
            f.writeText(content)
            return "Téléchargements/Telechargys/" + f.name
        }
        @JavascriptInterface fun applySettings(json: String) {}
    }
}
