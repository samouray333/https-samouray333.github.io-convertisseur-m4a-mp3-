package com.qmtech.lisys;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;

/**
 * Reconnaissance de texte hors ligne : Tesseract (compilé en WebAssembly) tourne dans une
 * WebView invisible. Les fichiers du moteur sont dans assets/ocr, servis par une fausse adresse
 * https://lisys.local/ ; rien ne part sur internet.
 */
public final class OcrEngine {

    interface Callback {
        void onProgress(int percent);
        void onDone(String text);
        void onError(String message);
    }

    private static final String HOST = "lisys.local";
    /** Taille maximale de l'image envoyée au moteur (le côté le plus long), pour rester rapide. */
    static final int MAX_SIDE = 2400;

    private final Activity activity;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final WebView web;
    private final File dir;
    private boolean ready;
    private String fatal;
    private int token;
    private final ArrayDeque<Object[]> queue = new ArrayDeque<Object[]>();
    private final Map<Integer, Callback> pending = new HashMap<Integer, Callback>();

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    OcrEngine(Activity a, ViewGroup host) {
        activity = a;
        dir = new File(a.getCacheDir(), "ocr");
        dir.mkdirs();
        web = new WebView(a);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        web.addJavascriptInterface(new Bridge(), "LisysOcr");
        web.setWebViewClient(new WebViewClient() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                return serve(r.getUrl());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) { return true; }
        });
        // La WebView doit être dans l'écran (même minuscule) pour que le JavaScript tourne normalement.
        host.addView(web, new ViewGroup.LayoutParams(1, 1));
        web.setAlpha(0f);
        web.loadUrl("https://" + HOST + "/ocr/ocr.html");
    }

    void destroy() {
        try {
            ((ViewGroup) web.getParent()).removeView(web);
        } catch (Exception ignored) {
        }
        web.destroy();
    }

    /** Sert les fichiers du moteur et les images à lire, sans passer par internet. */
    private WebResourceResponse serve(Uri u) {
        if (!HOST.equals(u.getHost())) return new WebResourceResponse("text/plain", "utf-8", null);
        String path = u.getPath() == null ? "" : u.getPath();
        try {
            InputStream in;
            if (path.startsWith("/image/")) {
                File f = new File(dir, new File(path.substring(7)).getName());
                in = new FileInputStream(f);
            } else if (path.startsWith("/ocr/")) {
                in = activity.getAssets().open("ocr/" + new File(path.substring(5)).getName());
            } else {
                return new WebResourceResponse("text/plain", "utf-8", 404, "Not found", null, null);
            }
            String mime = path.endsWith(".html") ? "text/html" : path.endsWith(".js") ? "text/javascript"
                    : path.endsWith(".wasm") ? "application/wasm" : path.endsWith(".jpg") ? "image/jpeg"
                    : "application/octet-stream";
            Map<String, String> headers = new HashMap<String, String>();
            headers.put("Access-Control-Allow-Origin", "*");
            return new WebResourceResponse(mime, mime.startsWith("text") ? "utf-8" : null, 200, "OK", headers, in);
        } catch (Exception e) {
            return new WebResourceResponse("text/plain", "utf-8", 404, "Not found", null, null);
        }
    }

    /** Lit le texte d'une image (fichier JPEG déjà préparé par {@link #prepare}). */
    void recognize(File image, Callback cb) {
        if (fatal != null) { cb.onError(fatal); return; }
        queue.add(new Object[]{image, cb});
        if (ready) next();
    }

    private boolean busy;

    private void next() {
        if (busy || queue.isEmpty()) return;
        Object[] job = queue.poll();
        File f = (File) job[0];
        Callback cb = (Callback) job[1];
        int t = ++token;
        pending.put(t, cb);
        busy = true;
        web.evaluateJavascript("window.ocrImage('https://" + HOST + "/image/" + f.getName() + "'," + t + ")", null);
    }

    public final class Bridge {
        @JavascriptInterface public void ready() {
            main.post(new Runnable() { @Override public void run() { ready = true; next(); } });
        }

        @JavascriptInterface public void progress(final int t, final int p) {
            main.post(new Runnable() { @Override public void run() {
                Callback cb = pending.get(t);
                if (cb != null) cb.onProgress(Math.max(0, Math.min(100, p)));
            } });
        }

        @JavascriptInterface public void result(final int t, final String text) {
            main.post(new Runnable() { @Override public void run() {
                Callback cb = pending.remove(t);
                busy = false;
                if (cb != null) cb.onDone(text == null ? "" : text);
                next();
            } });
        }

        @JavascriptInterface public void error(final int t, final String message) {
            main.post(new Runnable() { @Override public void run() {
                if (t == 0) {
                    // Le moteur n'a pas pu démarrer : toutes les demandes échouent.
                    fatal = "Le moteur de reconnaissance de texte n'a pas pu démarrer (" + message + ").";
                    for (Object[] job : queue) ((Callback) job[1]).onError(fatal);
                    queue.clear();
                    return;
                }
                Callback cb = pending.remove(t);
                busy = false;
                if (cb != null) cb.onError("Reconnaissance impossible : " + message);
                next();
            } });
        }
    }

    // ------------------------------------------------------------------ préparation des images

    /**
     * Ouvre une photo, la remet à l'endroit (rotation de l'appareil photo), la réduit
     * et l'enregistre en JPEG pour le moteur. À appeler hors du fil principal.
     */
    static File prepare(Activity a, Uri uri, String name) throws Exception {
        File dir = new File(a.getCacheDir(), "ocr");
        dir.mkdirs();
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inJustDecodeBounds = true;
        InputStream in = a.getContentResolver().openInputStream(uri);
        if (in == null) throw new Extractor.UserError("Impossible d'ouvrir l'image.");
        try { BitmapFactory.decodeStream(in, null, o); } finally { in.close(); }
        if (o.outWidth <= 0) throw new Extractor.UserError("Ce fichier n'est pas une image lisible.");
        int sample = 1;
        while (Math.max(o.outWidth, o.outHeight) / (sample * 2) >= MAX_SIDE) sample *= 2;
        BitmapFactory.Options o2 = new BitmapFactory.Options();
        o2.inSampleSize = sample;
        in = a.getContentResolver().openInputStream(uri);
        Bitmap bmp;
        try { bmp = BitmapFactory.decodeStream(in, null, o2); } finally { in.close(); }
        if (bmp == null) throw new Extractor.UserError("Ce fichier n'est pas une image lisible.");

        int rotation = 0;
        try {
            InputStream ex = a.getContentResolver().openInputStream(uri);
            try {
                int or = new ExifInterface(ex).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL);
                if (or == ExifInterface.ORIENTATION_ROTATE_90) rotation = 90;
                else if (or == ExifInterface.ORIENTATION_ROTATE_180) rotation = 180;
                else if (or == ExifInterface.ORIENTATION_ROTATE_270) rotation = 270;
            } finally {
                ex.close();
            }
        } catch (Exception ignored) {
        }
        return save(bmp, rotation, new File(dir, name));
    }

    /** Réduit (si besoin), tourne et enregistre une image pour le moteur. */
    static File save(Bitmap bmp, int rotation, File out) throws Exception {
        float scale = Math.min(1f, MAX_SIDE / (float) Math.max(bmp.getWidth(), bmp.getHeight()));
        if (rotation != 0 || scale < 1f) {
            Matrix m = new Matrix();
            m.postScale(scale, scale);
            m.postRotate(rotation);
            Bitmap r = Bitmap.createBitmap(bmp, 0, 0, bmp.getWidth(), bmp.getHeight(), m, true);
            if (r != bmp) bmp.recycle();
            bmp = r;
        }
        FileOutputStream os = new FileOutputStream(out);
        try {
            bmp.compress(Bitmap.CompressFormat.JPEG, 92, os);
        } finally {
            os.close();
            bmp.recycle();
        }
        return out;
    }
}
