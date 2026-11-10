package com.qmtech.telechargys

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.res.Configuration
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.URLUtil
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import mobile.Mobile

/** Navigateur intégré : repère les vidéos, sons et fichiers des pages et les envoie au moteur. */
class BrowserActivity : Activity() {
    private lateinit var web: WebView
    private lateinit var urlBox: EditText
    private lateinit var mediaBtn: TextView
    private lateinit var progress: ProgressBar
    private val found = LinkedHashMap<String, String>() // adresse -> type
    private val mediaExt = setOf("mp4", "webm", "mkv", "mov", "m4v", "m3u8", "mpd", "mp3", "m4a", "ogg", "opus", "flac", "wav", "aac")
    @Volatile private var lastTouch = 0L
    private val skipHosts = Regex("""(^|\.)(youtube\.com|googlevideo\.com|youtu\.be|netflix\.com|nflxvideo\.net|primevideo\.com|disneyplus\.com)$""")

    @SuppressLint("SetJavaScriptEnabled", "ClickableViewAccessibility")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        setContentView(R.layout.browser)
        val root = findViewById<View>(R.id.root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val b = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime())
            v.setPadding(b.left, b.top, b.right, b.bottom)
            WindowInsetsCompat.CONSUMED
        }
        val night = (resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
        WindowCompat.getInsetsController(window, window.decorView).apply { isAppearanceLightStatusBars = !night; isAppearanceLightNavigationBars = !night }
        runCatching { Engine.start(this) }

        web = findViewById(R.id.web)
        urlBox = findViewById(R.id.url)
        mediaBtn = findViewById(R.id.media)
        progress = findViewById(R.id.progress)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = true
            builtInZoomControls = true
            displayZoomControls = false
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportMultipleWindows(false)
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true)
        web.addJavascriptInterface(VideoBridge(), "TYBrowser")
        web.setOnTouchListener { _, _ -> lastTouch = System.currentTimeMillis(); false }
        web.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                found.clear(); refreshMedia()
                if (!urlBox.hasFocus()) urlBox.setText(url)
            }
            override fun onPageFinished(view: WebView, url: String) {
                val host = Uri.parse(url).host ?: ""
                if (!skipHosts.containsMatchIn(host)) view.evaluateJavascript(OVERLAY_JS, null)
            }
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val s = request.url.scheme ?: ""
                return s != "http" && s != "https" // liens d'applis (intent:, market:...) ignorés
            }
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                inspect(request.url)
                return null
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView, p: Int) {
                progress.progress = p
                progress.visibility = if (p >= 100) View.INVISIBLE else View.VISIBLE
            }
        }
        // téléchargement classique lancé par la page (lien vers un fichier)
        web.setDownloadListener { url, ua, cd, mime, _ ->
            if (!url.startsWith("http")) { Files.toast(this, "Ce type de lien (blob) ne peut pas être capté"); return@setDownloadListener }
            val name = if (!cd.isNullOrEmpty()) URLUtil.guessFileName(url, cd, mime) else ""
            send(url, name, ua)
        }

        urlBox.setOnEditorActionListener { _, action, ev ->
            if (action == EditorInfo.IME_ACTION_GO || ev?.keyCode == KeyEvent.KEYCODE_ENTER) { go(urlBox.text.toString()); true } else false
        }
        findViewById<View>(R.id.close).setOnClickListener { finish() }
        findViewById<View>(R.id.back).setOnClickListener { if (web.canGoBack()) web.goBack() }
        findViewById<View>(R.id.fwd).setOnClickListener { if (web.canGoForward()) web.goForward() }
        findViewById<View>(R.id.reload).setOnClickListener { web.reload() }
        findViewById<View>(R.id.grab).setOnClickListener { web.url?.let { send(it, "", web.settings.userAgentString) } }
        mediaBtn.setOnClickListener { showMedia() }

        val start = intent.getStringExtra("url").orEmpty()
        if (savedInstanceState != null) web.restoreState(savedInstanceState)
        else if (start.isNotEmpty()) go(start)
        else { urlBox.requestFocus() }
    }

    private fun go(input: String) {
        var u = input.trim()
        if (u.isEmpty()) return
        u = when {
            u.startsWith("http://") || u.startsWith("https://") -> u
            u.contains(".") && !u.contains(" ") -> "https://$u"
            else -> "https://duckduckgo.com/?q=" + Uri.encode(u)
        }
        (getSystemService(INPUT_METHOD_SERVICE) as InputMethodManager).hideSoftInputFromWindow(urlBox.windowToken, 0)
        urlBox.clearFocus()
        web.loadUrl(u)
    }

    /** Appelé pour chaque requête de la page (fil d'arrière-plan) : repère les médias par leur extension. */
    private fun inspect(u: Uri) {
        val host = u.host ?: return
        if (skipHosts.containsMatchIn(host)) return
        val ext = (u.lastPathSegment ?: "").substringAfterLast('.', "").lowercase()
        if (ext !in mediaExt) return
        val s = u.toString()
        runOnUiThread {
            if (found.size < 30 && !found.containsKey(s)) {
                found[s] = when (ext) { "m3u8" -> "Flux vidéo (HLS)"; "mpd" -> "Flux vidéo (DASH)"; else -> ext.uppercase() }
                refreshMedia()
            }
        }
    }

    private fun refreshMedia() {
        mediaBtn.text = "⬇ ${found.size}"
        mediaBtn.alpha = if (found.isEmpty()) 0.45f else 1f
    }

    private fun showMedia() {
        if (found.isEmpty()) { Files.toast(this, "Aucun média détecté : lance la lecture de la vidéo"); return }
        val urls = found.keys.toList().reversed()
        val labels = urls.map { u -> found[u] + " · " + (Uri.parse(u).lastPathSegment ?: u).take(60) }.toTypedArray()
        AlertDialog.Builder(this).setTitle("Médias détectés sur la page")
            .setItems(labels) { _, i ->
                val u = urls[i]
                val title = (web.title ?: "").replace(Regex("""[<>:"/\\|?*]"""), " ").trim().take(80)
                send(u, if (u.substringBefore('?').endsWith(".m3u8") && title.isNotEmpty()) "$title.mp4" else "", web.settings.userAgentString)
            }
            .setNegativeButton("Fermer", null).show()
    }

    /** Appelé par le bouton posé sur les vidéos ; refusé sans appui récent de l'utilisateur (une page ne peut pas lancer de téléchargement toute seule). */
    inner class VideoBridge {
        @JavascriptInterface
        fun video(src: String, title: String) {
            if (System.currentTimeMillis() - lastTouch > 3000) return
            runOnUiThread {
                val clean = title.replace(Regex("""[<>:"/\\|?*]"""), " ").trim().take(80).ifEmpty { "video" }
                val stream = found.keys.lastOrNull { val e = it.substringBefore('?').substringAfterLast('.').lowercase(); e == "m3u8" || e == "mpd" }
                val direct = if (src.startsWith("http")) src else ""
                val ext = direct.substringBefore('?').substringAfterLast('.', "").lowercase()
                when {
                    direct.isNotEmpty() && ext != "m3u8" && ext != "mpd" -> send(direct, "$clean.${if (ext in mediaExt) ext else "mp4"}", web.settings.userAgentString)
                    stream != null -> send(stream, "$clean.mp4", web.settings.userAgentString)
                    direct.isNotEmpty() -> send(direct, "$clean.mp4", web.settings.userAgentString)
                    found.isNotEmpty() -> showMedia()
                    else -> Files.toast(this@BrowserActivity, "Lance la lecture de la vidéo quelques secondes, puis réessaie")
                }
            }
        }
    }

    private fun send(url: String, name: String, ua: String?) {
        val cookies = CookieManager.getInstance().getCookie(url).orEmpty()
        val referer = web.url.orEmpty()
        Thread {
            val err = runCatching { Mobile.addNamed(url, name, referer, cookies, ua.orEmpty()) }.exceptionOrNull()
            runOnUiThread { Files.toast(this, if (err == null) "Téléchargement lancé dans Telechargys" else "Échec : ${err.message}") }
        }.start()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    @Deprecated("Retour : page précédente puis fermeture")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else finish()
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }
}

/** Bouton « Télécharger cette vidéo » posé en haut à droite de chaque vidéo de la page. */
private const val OVERLAY_JS = """
(function(){
  if (window.__tyOverlay) return; window.__tyOverlay = true;
  function deco(v){
    if (v.__ty) return; var r = v.getBoundingClientRect(); if (r.width < 160 || r.height < 90) return; v.__ty = true;
    var b = document.createElement('div');
    b.textContent = '⬇ Télécharger';
    b.style.cssText = 'position:absolute;z-index:2147483647;background:#0e9f6e;color:#fff;font:600 13px sans-serif;padding:7px 11px;border-radius:16px;box-shadow:0 2px 10px rgba(0,0,0,.4);';
    document.body.appendChild(b);
    function pos(){ var q = v.getBoundingClientRect(); if (!q.width) { b.style.display='none'; return; } b.style.display='block'; b.style.top = (q.top + window.scrollY + 8) + 'px'; b.style.left = (q.right + window.scrollX - b.offsetWidth - 8) + 'px'; }
    pos(); setInterval(pos, 700); window.addEventListener('scroll', pos, {passive:true});
    b.addEventListener('click', function(e){ e.preventDefault(); e.stopPropagation(); TYBrowser.video(v.currentSrc || v.src || '', document.title); b.textContent = 'Envoyé ✓'; setTimeout(function(){ b.textContent = '⬇ Télécharger'; }, 3000); }, true);
  }
  function scan(){ var vs = document.getElementsByTagName('video'); for (var i = 0; i < vs.length; i++) deco(vs[i]); }
  scan(); setInterval(scan, 1500);
})();
"""
