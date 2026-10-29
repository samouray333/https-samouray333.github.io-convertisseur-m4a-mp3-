package com.echomatras.lisys;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputMethodManager;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;

/**
 * Navigateur intégré : pour les sites qui ont besoin de JavaScript ou d'une connexion.
 * On navigue normalement, puis « Lire cette page » (ou seulement le texte sélectionné).
 */
public class WebActivity extends Activity {

    public static final String EXTRA_URL = "url";

    private final Handler main = new Handler(Looper.getMainLooper());
    private WebView web;
    private EditText address;
    private ProgressBar progress;
    private Button readBtn;
    private boolean working;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Ui.Palette pal = Ui.palette(this);
        Ui.systemBars(this, pal);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.setBackgroundColor(pal.bar);
        int p6 = Ui.dp(this, 6);
        bar.setPadding(p6, p6, p6, p6);
        TextView close = Ui.roundButton(this, "✕", "Fermer le navigateur", pal.bar, pal.barText, 44);
        close.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { finish(); } });
        bar.addView(close);
        address = new EditText(this);
        address.setSingleLine(true);
        address.setHint("Adresse du site ou recherche");
        address.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        address.setTextColor(pal.barText);
        address.setHintTextColor(pal.muted);
        address.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        address.setImeOptions(EditorInfo.IME_ACTION_GO);
        address.setSelectAllOnFocus(true);
        address.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override public boolean onEditorAction(TextView v, int a, KeyEvent e) {
                go(address.getText().toString());
                return true;
            }
        });
        bar.addView(address, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        TextView reload = Ui.roundButton(this, "⟳", "Recharger", pal.bar, pal.barText, 44);
        reload.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { web.reload(); } });
        bar.addView(reload);
        root.addView(bar);

        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        root.addView(progress, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 4)));

        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setBuiltInZoomControls(true);
        s.setDisplayZoomControls(false);
        s.setSupportZoom(true);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                String scheme = u.getScheme();
                if ("http".equals(scheme) || "https".equals(scheme)) {
                    String path = u.getPath() == null ? "" : u.getPath().toLowerCase();
                    // Lien vers un PDF : on le lit directement plutôt que de le télécharger.
                    if (path.endsWith(".pdf") || path.endsWith(".epub") || path.endsWith(".docx")) {
                        openInReader(u.toString());
                        return true;
                    }
                    return false;
                }
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) {}
                return true;
            }
            @Override public void onPageStarted(WebView v, String url, Bitmap icon) {
                if (!address.hasFocus()) address.setText(url);
            }
            @Override public void onPageFinished(WebView v, String url) {
                if (!address.hasFocus()) address.setText(url);
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public void onProgressChanged(WebView v, int p) {
                progress.setProgress(p);
                progress.setVisibility(p >= 100 ? View.INVISIBLE : View.VISIBLE);
            }
        });
        root.addView(web, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        LinearLayout bottom = new LinearLayout(this);
        bottom.setBackgroundColor(pal.bar);
        int p10 = Ui.dp(this, 10);
        bottom.setPadding(p10, p10, p10, p10);
        readBtn = Ui.bigButton(this, "🔊   Lire cette page", pal.button, pal.buttonText);
        readBtn.setGravity(Gravity.CENTER);
        readBtn.setContentDescription("Lire cette page à voix haute. Si du texte est sélectionné, seule la sélection est lue.");
        readBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { readPage(); } });
        bottom.addView(readBtn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(bottom);

        setContentView(root);

        String url = getIntent().getStringExtra(EXTRA_URL);
        if (state != null) web.restoreState(state);
        else if (url != null && url.trim().length() > 0) go(url);
        else {
            address.requestFocus();
            web.loadUrl("https://www.google.fr");
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    private void go(String text) {
        text = text.trim();
        if (text.length() == 0) return;
        String url;
        if (text.contains(" ") || !text.contains(".")) url = "https://www.google.fr/search?q=" + Uri.encode(text);
        else url = WebExtractor.normalizeUrl(text);
        web.loadUrl(url);
        address.clearFocus();
        web.requestFocus();
        InputMethodManager imm = (InputMethodManager) getSystemService(INPUT_METHOD_SERVICE);
        if (imm != null) imm.hideSoftInputFromWindow(address.getWindowToken(), 0);
    }

    private void openInReader(String url) {
        Intent i = new Intent(this, MainActivity.class).setAction(Intent.ACTION_VIEW).setData(Uri.parse(url));
        startActivity(i);
        finish();
    }

    private static final String JS = "(function(){try{var s=window.getSelection?window.getSelection().toString():'';"
            + "if(s&&s.replace(/\\s+/g,'').length>15)return 'SEL:'+s;}catch(e){}"
            + "return 'HTML:'+document.documentElement.outerHTML;})()";

    private void readPage() {
        if (working) return;
        working = true;
        readBtn.setText("Préparation…");
        web.evaluateJavascript(JS, new ValueCallback<String>() {
            @Override public void onReceiveValue(final String value) {
                final String url = web.getUrl();
                final String pageTitle = web.getTitle();
                new Thread(new Runnable() {
                    @Override public void run() { process(value, url, pageTitle); }
                }, "lecture-web").start();
            }
        });
    }

    private void process(String json, String url, String pageTitle) {
        String error = null;
        Library.Entry entry = null;
        try {
            String v = new JSONArray("[" + json + "]").getString(0);
            Extractor.Result r;
            String source;
            if (v.startsWith("SEL:")) {
                r = Extractor.fromText(pageTitle != null && pageTitle.length() > 0 ? pageTitle : "Sélection", v.substring(4));
                r.kind = "WEB";
                source = "selection:" + url + ":" + v.hashCode();
            } else {
                r = WebExtractor.fromHtml(v.startsWith("HTML:") ? v.substring(5) : v, url);
                source = url;
            }
            if (r.paragraphs.isEmpty()) error = "Aucun texte trouvé sur cette page.";
            else entry = Library.add(this, r, source);
        } catch (Throwable t) {
            error = "Impossible de lire cette page.";
        }
        final String err = error;
        final Library.Entry e = entry;
        main.post(new Runnable() {
            @Override public void run() {
                working = false;
                readBtn.setText("🔊   Lire cette page");
                if (isFinishing()) return;
                if (err != null) {
                    new AlertDialog.Builder(WebActivity.this).setMessage(err).setPositiveButton("OK", null).show();
                    return;
                }
                Intent i = new Intent(WebActivity.this, ReaderActivity.class);
                i.putExtra(ReaderActivity.EXTRA_ID, e.id);
                i.putExtra(ReaderActivity.EXTRA_AUTOPLAY, true);
                startActivity(i);
                Toast.makeText(WebActivity.this, "Astuce : sélectionne un passage pour ne lire que lui.", Toast.LENGTH_SHORT).show();
            }
        });
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }
}
