package com.qmtech.calorys;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Insets;
import android.net.Uri;
import android.app.AlarmManager;
import android.app.NotificationManager;
import android.os.Build;
import android.util.Base64;
import java.io.ByteArrayOutputStream;
import android.os.PowerManager;
import android.provider.Settings;
import android.os.Bundle;
import android.os.Environment;
import android.os.VibrationEffect;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.os.Vibrator;
import android.provider.MediaStore;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.webkit.JavascriptInterface;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;
import android.webkit.PermissionRequest;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * Calorys : coquille Android. L'interface est l'appli web embarquée dans assets/www,
 * servie sur une origine https locale (appassets.androidplatform.net) pour disposer
 * d'un contexte sécurisé (caméra) et d'un stockage stable.
 */
public class MainActivity extends Activity {
    static final String HOST = "appassets.androidplatform.net";
    static final String START_URL = "https://" + HOST + "/index.html";
    static final int REQ_FILE = 10;
    static final int REQ_CAMERA_PERM = 11;
    static final int REQ_NOTIF_PERM = 12;
    static final int REQ_HEALTH = 13;
    static final String PRIVACY_URL = "https://docs.google.com/document/d/1VvGzBh47u9nN8BlWkMAGq6YrBVnhbmG-kdH4GWH0DHY/view";

    private FrameLayout root;
    private WebView web;
    private ValueCallback<Uri[]> fileCallback;
    private Uri cameraOutput;
    private PermissionRequest pendingPermission;
    private CatalogStore catalog;
    private SyncServer sync;

    private static final Map<String, String> MIME = new HashMap<>();
    static {
        MIME.put("html", "text/html");
        MIME.put("js", "application/javascript");
        MIME.put("css", "text/css");
        MIME.put("json", "application/json");
        MIME.put("webmanifest", "application/manifest+json");
        MIME.put("svg", "image/svg+xml");
        MIME.put("png", "image/png");
        MIME.put("jpg", "image/jpeg");
        MIME.put("woff2", "font/woff2");
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        catalog = new CatalogStore(this);
        sync = new SyncServer(new SyncServer.Bridge() {
            @Override
            public void receive(final String body) {
                final String js = "window.__calorysSyncReceive && window.__calorysSyncReceive(" + JSONObject.quote(body) + ")";
                runOnUiThread(new Runnable() { @Override public void run() { web.evaluateJavascript(js, null); } });
            }
        });
        root = new FrameLayout(this);
        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        root.setBackgroundColor(night ? Color.parseColor("#0D1310") : Color.parseColor("#F4F7F5"));
        web = new WebView(this);
        web.setBackgroundColor(Color.TRANSPARENT);
        root.addView(web, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);
        setupInsets();
        registerBack();
        showPrivacyIfAsked(getIntent());
        takeShare(getIntent());

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setTextZoom(100);
        // Synchronisation : l'appli (origine https locale) contacte un autre téléphone en http sur le Wi-Fi.
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (!HOST.equals(u.getHost())) return null;
                return serveAsset(u.getPath());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (HOST.equals(u.getHost())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (ActivityNotFoundException e) { /* ignore */ }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                boolean wantsVideo = false;
                for (String r : request.getResources()) if (PermissionRequest.RESOURCE_VIDEO_CAPTURE.equals(r)) wantsVideo = true;
                if (!wantsVideo) { request.deny(); return; }
                if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
                } else {
                    pendingPermission = request;
                    requestPermissions(new String[]{Manifest.permission.CAMERA}, REQ_CAMERA_PERM);
                }
            }

            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                return openChooser(params);
            }
        });

        web.addJavascriptInterface(new Bridge(), "CalorysNative");
        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else web.loadUrl(START_URL);
    }

    private void setupInsets() {
        if (Build.VERSION.SDK_INT < 30) return;
        getWindow().setDecorFitsSystemWindows(false);
        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override
            public WindowInsets onApplyWindowInsets(View v, WindowInsets insets) {
                Insets i = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                v.setPadding(i.left, i.top, i.right, i.bottom);
                return WindowInsets.CONSUMED;
            }
        });
    }

    private WebResourceResponse serveAsset(String path) {
        if (path == null || path.equals("/") || path.isEmpty()) path = "/index.html";
        String ext = path.substring(path.lastIndexOf('.') + 1).toLowerCase();
        String mime = MIME.containsKey(ext) ? MIME.get(ext) : "application/octet-stream";
        Map<String, String> headers = new HashMap<>();
        headers.put("Cache-Control", "no-cache");
        try {
            InputStream in = getAssets().open("www" + path);
            WebResourceResponse r = new WebResourceResponse(mime, "UTF-8", in);
            r.setResponseHeaders(headers);
            return r;
        } catch (Exception e) {
            WebResourceResponse r = new WebResourceResponse("text/plain", "UTF-8", new ByteArrayInputStream(new byte[0]));
            r.setStatusCodeAndReasonPhrase(404, "Not Found");
            return r;
        }
    }

    private boolean openChooser(WebChromeClient.FileChooserParams params) {
        boolean image = false;
        for (String t : params.getAcceptTypes()) if (t != null && t.startsWith("image")) image = true;
        Intent pick;
        if (image) {
            Intent gallery = new Intent(Intent.ACTION_GET_CONTENT);
            gallery.addCategory(Intent.CATEGORY_OPENABLE);
            gallery.setType("image/*");
            pick = Intent.createChooser(gallery, "Photo du code-barres");
            if (checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                Intent cam = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                cameraOutput = FilesProvider.uriFor(FilesProvider.newPhotoFile(this));
                cam.putExtra(MediaStore.EXTRA_OUTPUT, cameraOutput);
                cam.setClipData(ClipData.newRawUri("", cameraOutput));
                cam.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                pick.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{cam});
            } else {
                cameraOutput = null;
            }
        } else {
            cameraOutput = null;
            pick = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            pick.addCategory(Intent.CATEGORY_OPENABLE);
            pick.setType("*/*");
            pick.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/json", "text/plain", "application/octet-stream"});
        }
        try {
            startActivityForResult(pick, REQ_FILE);
            return true;
        } catch (ActivityNotFoundException e) {
            fileCallback = null;
            return false;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode != REQ_FILE) { super.onActivityResult(requestCode, resultCode, data); return; }
        if (fileCallback == null) return;
        Uri[] result = null;
        if (resultCode == RESULT_OK) {
            if (data != null && data.getData() != null) result = new Uri[]{data.getData()};
            else if (cameraOutput != null) result = new Uri[]{cameraOutput};
        }
        fileCallback.onReceiveValue(result);
        fileCallback = null;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        if (requestCode == REQ_HEALTH) {
            web.evaluateJavascript("window.__calorysHealth && window.__calorysHealth('perm')", null);
            return;
        }
        if (requestCode == REQ_CAMERA_PERM && pendingPermission != null) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                pendingPermission.grant(new String[]{PermissionRequest.RESOURCE_VIDEO_CAPTURE});
            } else {
                pendingPermission.deny();
            }
            pendingPermission = null;
        }
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() { handleBack(); }

    /* Health Connect ouvre l'appli avec VIEW_PERMISSION_USAGE pour montrer la politique de confidentialité. */
    /* Fichier partagé vers Calorys (rapport de balance, export CSV) : gardé jusqu'à ce que l'appli web le réclame. */
    private volatile String sharedJson = null;

    private void takeShare(Intent i) {
        if (i == null || !Intent.ACTION_SEND.equals(i.getAction())) return;
        final Uri u = i.getParcelableExtra(Intent.EXTRA_STREAM);
        final String type = i.getType();
        if (u == null) return;
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    InputStream in = getContentResolver().openInputStream(u);
                    ByteArrayOutputStream bo = new ByteArrayOutputStream();
                    byte[] buf = new byte[1 << 16];
                    int n;
                    try { while ((n = in.read(buf)) > 0) { bo.write(buf, 0, n); if (bo.size() > 15 * 1024 * 1024) throw new Exception("trop lourd"); } }
                    finally { in.close(); }
                    String name = u.getLastPathSegment() == null ? "fichier" : u.getLastPathSegment();
                    JSONObject o = new JSONObject();
                    o.put("name", name);
                    o.put("mime", type == null ? "" : type);
                    o.put("b64", Base64.encodeToString(bo.toByteArray(), Base64.NO_WRAP));
                    sharedJson = o.toString();
                    runOnUiThread(new Runnable() { @Override public void run() { web.evaluateJavascript("window.__calorysShared && window.__calorysShared()", null); } });
                } catch (Exception e) {
                    runOnUiThread(new Runnable() { @Override public void run() { Toast.makeText(MainActivity.this, "Fichier partagé illisible", Toast.LENGTH_LONG).show(); } });
                }
            }
        }).start();
    }

    private void showPrivacyIfAsked(Intent i) {
        if (i == null || !"android.intent.action.VIEW_PERMISSION_USAGE".equals(i.getAction())) return;
        try { startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(PRIVACY_URL))); } catch (Exception e) { /* ignore */ }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        showPrivacyIfAsked(intent);
        takeShare(intent);
    }

    /* Android 13+ : retour (et retour prédictif d'Android 16) via OnBackInvokedDispatcher. */
    private void registerBack() {
        if (Build.VERSION.SDK_INT < 33) return;
        getOnBackInvokedDispatcher().registerOnBackInvokedCallback(OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                new OnBackInvokedCallback() { @Override public void onBackInvoked() { handleBack(); } });
    }

    private void handleBack() {
        web.evaluateJavascript("(window.calorysBack && window.calorysBack()) ? 'yes' : 'no'", new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String v) {
                if (v == null || !v.contains("yes")) moveTaskToBack(true);
            }
        });
    }

    @Override
    protected void onPause() {
        web.evaluateJavascript("window.Platform && Platform.flush()", null);
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onDestroy() {
        if (sync != null) sync.stop();
        if (web != null) web.destroy();
        super.onDestroy();
    }

    /* ---------- Fichiers ---------- */

    static byte[] utf8(String s) { return s.getBytes(StandardCharsets.UTF_8); }

    /** Enregistre dans Documents/Calorys (Android 10+) ; renvoie un chemin lisible ou "ERR:message". */
    String saveToDocuments(String name, String mime, String content) {
        byte[] bytes = utf8(name.endsWith(".csv") ? "﻿" + content : content);
        try {
            if (Build.VERSION.SDK_INT >= 29) {
                ContentResolver cr = getContentResolver();
                ContentValues v = new ContentValues();
                v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                v.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOCUMENTS + "/Calorys");
                Uri uri = cr.insert(MediaStore.Files.getContentUri("external"), v);
                if (uri == null) return "ERR:impossible de créer le fichier";
                OutputStream os = cr.openOutputStream(uri);
                try { os.write(bytes); } finally { os.close(); }
                return "Documents/Calorys/" + name;
            }
            File dir = new File(getExternalFilesDir(Environment.DIRECTORY_DOCUMENTS), "Calorys");
            if (!dir.exists() && !dir.mkdirs()) return "ERR:dossier inaccessible";
            File f = new File(dir, name);
            FileOutputStream os = new FileOutputStream(f);
            try { os.write(bytes); } finally { os.close(); }
            return f.getAbsolutePath();
        } catch (Exception e) {
            return "ERR:" + e.getMessage();
        }
    }

    static void writeAtomic(File f, byte[] bytes) throws Exception {
        File tmp = new File(f.getPath() + ".tmp");
        FileOutputStream os = new FileOutputStream(tmp);
        try { os.write(bytes); os.getFD().sync(); } finally { os.close(); }
        if (!tmp.renameTo(f)) throw new Exception("rename");
    }

    static String readAll(File f) throws Exception {
        FileInputStream in = new FileInputStream(f);
        try {
            byte[] buf = new byte[(int) f.length()];
            int off = 0, n;
            while (off < buf.length && (n = in.read(buf, off, buf.length - off)) > 0) off += n;
            return new String(buf, 0, off, StandardCharsets.UTF_8);
        } finally { in.close(); }
    }

    /* ---------- Pont JavaScript ---------- */

    class Bridge {
        @JavascriptInterface
        public String platform() { return "android"; }

        @JavascriptInterface
        public String saveFile(String name, String mime, String content) {
            return saveToDocuments(safeName(name), mime, content);
        }

        @JavascriptInterface
        public void shareFile(String name, final String mime, String content) {
            try {
                final File f = FilesProvider.shareFile(MainActivity.this, safeName(name));
                writeAtomic(f, utf8(name.endsWith(".csv") ? "﻿" + content : content));
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        Uri uri = FilesProvider.uriFor(f);
                        Intent send = new Intent(Intent.ACTION_SEND);
                        send.setType(mime);
                        send.putExtra(Intent.EXTRA_STREAM, uri);
                        send.setClipData(ClipData.newRawUri("", uri));
                        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(Intent.createChooser(send, "Partager"));
                    }
                });
            } catch (final Exception e) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() { Toast.makeText(MainActivity.this, "Partage impossible : " + e.getMessage(), Toast.LENGTH_LONG).show(); }
                });
            }
        }

        @JavascriptInterface
        public void saveBackup(String json) {
            try { writeAtomic(new File(getFilesDir(), "calorys-data.json"), utf8(json)); } catch (Exception e) { /* ignore */ }
        }

        @JavascriptInterface
        public String loadBackup() {
            File f = new File(getFilesDir(), "calorys-data.json");
            if (!f.exists()) return null;
            try { return readAll(f); } catch (Exception e) { return null; }
        }

        @JavascriptInterface
        public void setBars(final boolean dark, final String color) {
            runOnUiThread(new Runnable() {
                @Override
                @SuppressWarnings("deprecation")
                public void run() {
                    int c;
                    try { c = Color.parseColor(color); } catch (Exception e) { c = dark ? Color.BLACK : Color.WHITE; }
                    root.setBackgroundColor(c);
                    if (Build.VERSION.SDK_INT >= 30) {
                        WindowInsetsController ic = getWindow().getInsetsController();
                        if (ic != null) {
                            int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                            ic.setSystemBarsAppearance(dark ? 0 : mask, mask);
                        }
                    } else {
                        getWindow().setStatusBarColor(c);
                        getWindow().setNavigationBarColor(c);
                        int f = getWindow().getDecorView().getSystemUiVisibility();
                        int light = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
                        getWindow().getDecorView().setSystemUiVisibility(dark ? (f & ~light) : (f | light));
                    }
                    if (Build.VERSION.SDK_INT < 35) {
                        getWindow().setStatusBarColor(c);
                        getWindow().setNavigationBarColor(c);
                    }
                }
            });
        }

        /* ---- Catalogue hors ligne ---- */
        @JavascriptInterface
        public String catalogStatus() { return catalog.status(); }

        @JavascriptInterface
        public void catalogInstall(String manifest, String sources) {
            catalog.install(manifest, sources, new CatalogStore.Listener() {
                @Override
                public void onProgress(final String state, final double progress, final String message) {
                    final String js = "window.__calorysCatalog && window.__calorysCatalog(" + JSONObject.quote(state) + "," + progress + "," + JSONObject.quote(message == null ? "" : message) + ")";
                    runOnUiThread(new Runnable() { @Override public void run() { web.evaluateJavascript(js, null); } });
                }
            });
        }

        @JavascriptInterface
        public String catalogSearch(String match, int limit) { return catalog.search(match, limit); }

        @JavascriptInterface
        public String catalogBarcode(String code) { return catalog.barcode(code); }

        @JavascriptInterface
        public void catalogRemove() { catalog.remove(); }

        /* ---- Synchronisation sur le Wi-Fi local ---- */
        @JavascriptInterface
        public String syncStart(int port) {
            try {
                int p = sync.start(port);
                org.json.JSONArray ips = new org.json.JSONArray();
                for (String a : SyncServer.addresses()) ips.put(a);
                runOnUiThread(new Runnable() { @Override public void run() { getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON); } });
                return new JSONObject().put("port", p).put("ips", ips).toString();
            } catch (Exception e) {
                return "{\"error\":" + JSONObject.quote("Impossible d'ouvrir la synchronisation : " + e.getMessage()) + "}";
            }
        }

        @JavascriptInterface
        public void syncOffer(String blob) { sync.setOffer(blob); }

        @JavascriptInterface
        public void syncResult(String json) { sync.setResult(json); }

        @JavascriptInterface
        public void syncStop() {
            sync.stop();
            runOnUiThread(new Runnable() { @Override public void run() { getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON); } });
        }

        @JavascriptInterface
        public String deviceName() { return (Build.MANUFACTURER + " " + Build.MODEL).trim(); }

        /* ---- Rappels ---- */
        @JavascriptInterface
        public void setReminders(final String json) {
            ReminderReceiver.schedule(MainActivity.this, json);
            boolean any = json != null && (json.contains("\"id\"") || json.matches(".*\"fastEnd\":[1-9].*"));
            if (any && Build.VERSION.SDK_INT >= 33 && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED) {
                runOnUiThread(new Runnable() { @Override public void run() { requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, REQ_NOTIF_PERM); } });
            }
        }

        /** État de ce qui peut empêcher les rappels : autorisation, heure exacte, économie de batterie. */
        @JavascriptInterface
        public String notifStatus() {
            try {
                NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
                AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
                PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                JSONObject o = new JSONObject();
                o.put("allowed", nm != null && nm.areNotificationsEnabled());
                o.put("exact", am != null && ReminderReceiver.canExact(am));
                o.put("battery", pm != null && pm.isIgnoringBatteryOptimizations(getPackageName()));
                o.put("batteryDirect", batteryDirect());
                return o.toString();
            } catch (Exception e) { return "{}"; }
        }

        /** Fichier partagé en attente (JSON {name, mime, b64}) ou null ; une seule fois. */
        @JavascriptInterface
        public String takeShared() { String s = sharedJson; sharedJson = null; return s; }

        /* ---- Balance connectée (Health Connect) ---- */
        @JavascriptInterface
        public String healthStatus() {
            try {
                JSONObject o = new JSONObject();
                boolean ok = Health.available(MainActivity.this);
                o.put("available", ok);
                o.put("sdk", Build.VERSION.SDK_INT);
                o.put("weight", ok && checkSelfPermission(Health.READ_WEIGHT) == PackageManager.PERMISSION_GRANTED);
                o.put("fat", ok && checkSelfPermission(Health.READ_BODY_FAT) == PackageManager.PERMISSION_GRANTED);
                return o.toString();
            } catch (Exception e) { return "{}"; }
        }

        @JavascriptInterface
        public void healthRequest() {
            if (!Health.available(MainActivity.this)) return;
            runOnUiThread(new Runnable() { @Override public void run() { requestPermissions(Health.permissions(), REQ_HEALTH); } });
        }

        @JavascriptInterface
        public void healthSettings() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        startActivity(new Intent("android.health.connect.action.MANAGE_HEALTH_PERMISSIONS").putExtra(Intent.EXTRA_PACKAGE_NAME, getPackageName()));
                    } catch (Exception e) {
                        try { startActivity(new Intent("android.health.connect.action.HEALTH_HOME_SETTINGS")); } catch (Exception e2) { /* ignore */ }
                    }
                }
            });
        }

        @JavascriptInterface
        public void healthRead(final double sinceMs) {
            if (!Health.available(MainActivity.this)) return;
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Health.read(MainActivity.this, (long) sinceMs, new Health.Done() {
                        @Override
                        public void done(String json) {
                            web.evaluateJavascript("window.__calorysHealth && window.__calorysHealth('data', " + JSONObject.quote(json) + ")", null);
                        }
                    });
                }
            });
        }

        /** Lecture à voix haute immédiate (bouton « Tester la voix »). */
        @JavascriptInterface
        public boolean speak(final String text) {
            if (!Speaker.canSpeak(MainActivity.this)) return false;
            runOnUiThread(new Runnable() { @Override public void run() { Speaker.say(MainActivity.this, text, 20000, null); } });
            return true;
        }

        /** Version Play Store : pas de demande directe, on ouvre la liste des applis. */
        private boolean batteryDirect() {
            return checkSelfPermission("android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS") == PackageManager.PERMISSION_GRANTED;
        }

        @JavascriptInterface
        public void testNotif() {
            ReminderReceiver.notify(MainActivity.this, 98, "Test Calorys", "Les notifications arrivent bien sur ce téléphone.");
        }

        /** what : "notif" (réglages des notifications), "battery" (ne pas optimiser la batterie), "exact" (alarmes). */
        @JavascriptInterface
        public void openSettings(final String what) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Intent i;
                    if ("battery".equals(what)) i = batteryDirect()
                            ? new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName()))
                            : new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS);
                    else if ("exact".equals(what) && Build.VERSION.SDK_INT >= 31) i = new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:" + getPackageName()));
                    else i = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName());
                    try { startActivity(i); }
                    catch (ActivityNotFoundException e) {
                        try { startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName()))); } catch (Exception e2) { /* ignore */ }
                    }
                }
            });
        }

        /* ---- Impression / PDF du rapport ---- */
        @JavascriptInterface
        public void printPage(final String name) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    PrintManager pm = (PrintManager) getSystemService(Context.PRINT_SERVICE);
                    if (pm == null) return;
                    String n = safeName(name);
                    pm.print(n, web.createPrintDocumentAdapter(n), new PrintAttributes.Builder().setMediaSize(PrintAttributes.MediaSize.ISO_A4).build());
                }
            });
        }

        @JavascriptInterface
        public void vibrate(int ms) {
            Vibrator v = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
            if (v == null || !v.hasVibrator()) return;
            v.vibrate(VibrationEffect.createOneShot(Math.max(1, Math.min(ms, 200)), VibrationEffect.DEFAULT_AMPLITUDE));
        }
    }

    static String safeName(String n) {
        String s = n == null ? "calorys.txt" : n.replaceAll("[^A-Za-z0-9._-]", "_");
        return s.isEmpty() ? "calorys.txt" : s;
    }

}
