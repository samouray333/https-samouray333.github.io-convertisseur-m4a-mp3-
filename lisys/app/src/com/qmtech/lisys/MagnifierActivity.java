package com.qmtech.lisys;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.ColorMatrix;
import android.graphics.ColorMatrixColorFilter;
import android.graphics.Paint;
import android.graphics.Rect;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CameraMetadata;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Size;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.ScaleGestureDetector;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/**
 * Loupe : l'appareil photo grossit en direct, avec couleurs renforcées, lampe, image figée
 * et lecture à voix haute du texte visible.
 */
public class MagnifierActivity extends Activity {

    private static final int REQ_CAMERA = 1;
    private static final String[] FILTER_NAMES = {Tr.t("Couleurs normales"), Tr.t("Contraste renforcé"), Tr.t("Blanc sur noir"), Tr.t("Jaune sur noir"), Tr.t("Noir sur jaune")};

    private Ui.Palette pal;
    private FrameLayout stage;
    private TextureView texture;
    private ImageView frozen;
    private TextView zoomLabel, freezeBtn, torchBtn;

    private CameraDevice camera;
    private CameraCaptureSession session;
    private CaptureRequest.Builder request;
    private CameraCharacteristics chars;
    private HandlerThread thread;
    private Handler bg;
    private Size previewSize;
    private float zoom = 2f, maxZoom = 8f;
    private int filter;
    private boolean torch, isFrozen;
    private float frozenScale = 1f;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (!Features.require(this, Tr.t("La loupe"))) { finish(); return; }
        pal = Ui.palette(this);
        Ui.systemBars(this, pal);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(0xFF000000);

        stage = new FrameLayout(this);
        texture = new TextureView(this);
        texture.setContentDescription(Tr.t("Image de l'appareil photo, agrandie"));
        stage.addView(texture, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT, Gravity.CENTER));
        frozen = new ImageView(this);
        frozen.setScaleType(ImageView.ScaleType.FIT_CENTER);
        frozen.setVisibility(View.GONE);
        frozen.setContentDescription(Tr.t("Image figée"));
        stage.addView(frozen, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        product = Ui.label(this, "", 22, 0xFF000000, true);
        product.setBackgroundColor(0xF0FFEB3B);
        int pp = Ui.dp(this, 14);
        product.setPadding(pp, pp, pp, pp);
        product.setVisibility(View.GONE);
        product.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { Speaker.say(MagnifierActivity.this, product.getText().toString(), null); } });
        stage.addView(product, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP));
        root.addView(stage, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        final ScaleGestureDetector pinch = new ScaleGestureDetector(this, new ScaleGestureDetector.SimpleOnScaleGestureListener() {
            @Override public boolean onScale(ScaleGestureDetector d) {
                if (isFrozen) {
                    frozenScale = Math.max(1f, Math.min(8f, frozenScale * d.getScaleFactor()));
                    frozen.setScaleX(frozenScale);
                    frozen.setScaleY(frozenScale);
                } else {
                    setZoom(zoom * d.getScaleFactor(), false);
                }
                return true;
            }
        });
        stage.setOnTouchListener(new View.OnTouchListener() {
            float lastX, lastY;
            @Override public boolean onTouch(View v, MotionEvent e) {
                pinch.onTouchEvent(e);
                // Image figée : on la déplace avec un doigt.
                if (isFrozen && e.getPointerCount() == 1) {
                    if (e.getActionMasked() == MotionEvent.ACTION_DOWN) { lastX = e.getX(); lastY = e.getY(); }
                    else if (e.getActionMasked() == MotionEvent.ACTION_MOVE) {
                        frozen.setTranslationX(frozen.getTranslationX() + e.getX() - lastX);
                        frozen.setTranslationY(frozen.getTranslationY() + e.getY() - lastY);
                        lastX = e.getX(); lastY = e.getY();
                    }
                }
                return true;
            }
        });

        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setBackgroundColor(pal.bar);
        panel.setPadding(Ui.dp(this, 8), Ui.dp(this, 8), Ui.dp(this, 8), Ui.dp(this, 8));
        LinearLayout row1 = row(), row2 = row();
        btn(row1, "−", Tr.t("Moins de zoom"), new Runnable() { public void run() { setZoom(zoom / 1.4f, true); } });
        zoomLabel = Ui.label(this, "", 22, pal.barText, true);
        zoomLabel.setGravity(Gravity.CENTER);
        row1.addView(zoomLabel, new LinearLayout.LayoutParams(0, Ui.dp(this, 64), 1.4f));
        btn(row1, "+", Tr.t("Plus de zoom"), new Runnable() { public void run() { setZoom(zoom * 1.4f, true); } });
        btn(row2, "◐", Tr.t("Changer les couleurs"), new Runnable() { public void run() { nextFilter(); } });
        torchBtn = btn(row2, "💡", Tr.t("Lampe"), new Runnable() { public void run() { toggleTorch(); } });
        freezeBtn = btn(row2, "❚❚", Tr.t("Figer l'image"), new Runnable() { public void run() { toggleFreeze(); } });
        btn(row2, "🔊", Tr.t("Lire le texte"), new Runnable() { public void run() { readText(); } });
        btn(row1, "🏷", Tr.t("Lire le code-barres d'un produit"), new Runnable() { public void run() { toggleScan(); } });
        panel.addView(row1);
        panel.addView(row2);
        root.addView(panel);
        Ui.setContent(this, root);
        updateZoomLabel();

        texture.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
            @Override public void onSurfaceTextureAvailable(SurfaceTexture s, int w, int h) { openCamera(); }
            @Override public void onSurfaceTextureSizeChanged(SurfaceTexture s, int w, int h) { fitTexture(); }
            @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture s) { return true; }
            @Override public void onSurfaceTextureUpdated(SurfaceTexture s) {}
        });
        if (checkSelfPermission(android.Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.CAMERA}, REQ_CAMERA);
        }
        Speaker.say(this, Tr.t("Loupe. Vise le texte. Pince l'écran ou utilise plus et moins pour grossir."));
    }

    private LinearLayout row() {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setGravity(Gravity.CENTER);
        return r;
    }

    private TextView btn(LinearLayout row, String glyph, String desc, final Runnable r) {
        TextView t = Ui.roundButton(this, glyph, desc, pal.surface, pal.text, 64);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, Ui.dp(this, 64), 1);
        lp.setMargins(Ui.dp(this, 4), Ui.dp(this, 4), Ui.dp(this, 4), Ui.dp(this, 4));
        t.setLayoutParams(lp);
        Ui.background(t, pal.surface, Ui.dp(this, 16), 0x33888888);
        t.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { Ui.tick(v); r.run(); } });
        row.addView(t);
        return t;
    }

    @Override
    protected void onResume() {
        super.onResume();
        thread = new HandlerThread("loupe");
        thread.start();
        bg = new Handler(thread.getLooper());
        if (texture.isAvailable()) openCamera();
    }

    @Override
    protected void onPause() {
        scanning = false;
        closeCamera();
        if (thread != null) { thread.quitSafely(); thread = null; }
        super.onPause();
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] p, int[] res) {
        if (req != REQ_CAMERA) return;
        if (res.length > 0 && res[0] == PackageManager.PERMISSION_GRANTED) { if (texture.isAvailable()) openCamera(); }
        else {
            Toast.makeText(this, Tr.t("La loupe a besoin de l'appareil photo."), Toast.LENGTH_LONG).show();
            finish();
        }
    }

    // ------------------------------------------------------------------ appareil photo

    private void openCamera() {
        if (camera != null || bg == null) return;
        if (checkSelfPermission(android.Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) return;
        CameraManager cm = (CameraManager) getSystemService(CAMERA_SERVICE);
        try {
            String id = null;
            for (String c : cm.getCameraIdList()) {
                CameraCharacteristics ch = cm.getCameraCharacteristics(c);
                Integer facing = ch.get(CameraCharacteristics.LENS_FACING);
                if (facing != null && facing == CameraCharacteristics.LENS_FACING_BACK) { id = c; chars = ch; break; }
            }
            if (id == null) { Toast.makeText(this, Tr.t("Pas d'appareil photo arrière."), Toast.LENGTH_LONG).show(); return; }
            Float mz = chars.get(CameraCharacteristics.SCALER_AVAILABLE_MAX_DIGITAL_ZOOM);
            maxZoom = mz != null ? Math.max(1f, mz) : 4f;
            zoom = Math.min(zoom, maxZoom);
            StreamConfigurationMap map = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            previewSize = choose(map.getOutputSizes(SurfaceTexture.class));
            cm.openCamera(id, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice c) { camera = c; startPreview(); }
                @Override public void onDisconnected(CameraDevice c) { c.close(); camera = null; }
                @Override public void onError(CameraDevice c, int e) { c.close(); camera = null; }
            }, bg);
        } catch (Exception e) {
            Toast.makeText(this, Tr.t("Impossible d'ouvrir l'appareil photo."), Toast.LENGTH_LONG).show();
        }
    }

    /** Taille d'aperçu : la plus grande jusqu'à 1920 de large (net, mais fluide). */
    private static Size choose(Size[] sizes) {
        Size best = sizes[0];
        for (Size s : sizes) {
            if (s.getWidth() > 1920) continue;
            if (best.getWidth() > 1920 || s.getWidth() * s.getHeight() > best.getWidth() * best.getHeight()) best = s;
        }
        return best;
    }

    private void startPreview() {
        try {
            SurfaceTexture st = texture.getSurfaceTexture();
            st.setDefaultBufferSize(previewSize.getWidth(), previewSize.getHeight());
            runOnUiThread(new Runnable() { public void run() { fitTexture(); } });
            Surface surface = new Surface(st);
            request = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
            request.addTarget(surface);
            request.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE);
            request.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON);
            camera.createCaptureSession(Arrays.asList(surface), new CameraCaptureSession.StateCallback() {
                @Override public void onConfigured(CameraCaptureSession s) { session = s; applyRequest(); }
                @Override public void onConfigureFailed(CameraCaptureSession s) {}
            }, bg);
        } catch (Exception ignored) {
        }
    }

    /** Aperçu sans déformation : la vidéo est en paysage, l'écran en portrait. */
    private void fitTexture() {
        if (previewSize == null) return;
        int w = stage.getWidth(), h = stage.getHeight();
        if (w == 0 || h == 0) return;
        float aspect = (float) previewSize.getWidth() / previewSize.getHeight(); // > 1
        int tw = w, th = Math.round(w * aspect);
        if (th < h) { th = h; tw = Math.round(h / aspect); } // remplit l'écran (recadré au centre)
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(tw, th, Gravity.CENTER);
        texture.setLayoutParams(lp);
    }

    private void applyRequest() {
        if (session == null || request == null || chars == null) return;
        try {
            Rect active = chars.get(CameraCharacteristics.SENSOR_INFO_ACTIVE_ARRAY_SIZE);
            if (active != null) {
                int cw = Math.round(active.width() / zoom), ch = Math.round(active.height() / zoom);
                int cx = active.centerX(), cy = active.centerY();
                request.set(CaptureRequest.SCALER_CROP_REGION, new Rect(cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2));
            }
            request.set(CaptureRequest.FLASH_MODE, torch ? CameraMetadata.FLASH_MODE_TORCH : CameraMetadata.FLASH_MODE_OFF);
            if (!isFrozen) session.setRepeatingRequest(request.build(), null, bg);
        } catch (CameraAccessException | IllegalStateException ignored) {
        }
    }

    private void closeCamera() {
        try { if (session != null) session.close(); } catch (Exception ignored) {}
        try { if (camera != null) camera.close(); } catch (Exception ignored) {}
        session = null;
        camera = null;
    }

    // ------------------------------------------------------------------ commandes

    private void setZoom(float z, boolean announce) {
        if (isFrozen) {
            frozenScale = Math.max(1f, Math.min(8f, frozenScale * (z / zoom)));
            frozen.setScaleX(frozenScale);
            frozen.setScaleY(frozenScale);
            return;
        }
        zoom = Math.max(1f, Math.min(maxZoom, z));
        updateZoomLabel();
        applyRequest();
        if (announce) Speaker.say(this, Tr.t("Zoom ") + String.format(Locale.FRANCE, "%.1f", zoom));
    }

    private void updateZoomLabel() {
        zoomLabel.setText(String.format(Locale.FRANCE, "×%.1f", zoom));
        zoomLabel.setContentDescription(Tr.t("Zoom ") + String.format(Locale.FRANCE, "%.1f", zoom));
    }

    private void nextFilter() {
        filter = (filter + 1) % FILTER_NAMES.length;
        ColorMatrix m = matrix(filter);
        Paint p = new Paint();
        if (m != null) p.setColorFilter(new ColorMatrixColorFilter(m));
        texture.setLayerType(m == null ? View.LAYER_TYPE_NONE : View.LAYER_TYPE_HARDWARE, m == null ? null : p);
        frozen.setColorFilter(m == null ? null : new ColorMatrixColorFilter(m));
        Speaker.say(this, FILTER_NAMES[filter]);
        Toast.makeText(this, FILTER_NAMES[filter], Toast.LENGTH_SHORT).show();
    }

    /** Filtres de couleurs pour mieux lire (niveaux de gris très contrastés, inversion, jaune sur noir…). */
    static ColorMatrix matrix(int f) {
        if (f == 0) return null;
        float c = 2.2f, o = -128 * (c - 1); // contraste fort autour du gris moyen
        float r = 0.299f * c, g = 0.587f * c, b = 0.114f * c;
        switch (f) {
            case 1: return new ColorMatrix(new float[]{r, g, b, 0, o, r, g, b, 0, o, r, g, b, 0, o, 0, 0, 0, 1, 0});
            case 2: return new ColorMatrix(new float[]{-r, -g, -b, 0, 255 - o, -r, -g, -b, 0, 255 - o, -r, -g, -b, 0, 255 - o, 0, 0, 0, 1, 0});
            case 3: return new ColorMatrix(new float[]{-r, -g, -b, 0, 255 - o, -r, -g, -b, 0, 255 - o, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0});
            default: return new ColorMatrix(new float[]{r, g, b, 0, o, r, g, b, 0, o, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0});
        }
    }

    private void toggleTorch() {
        Boolean has = chars == null ? null : chars.get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
        if (has == null || !has) { Speaker.say(this, Tr.t("Pas de lampe sur ce téléphone.")); return; }
        torch = !torch;
        torchBtn.setContentDescription(torch ? Tr.t("Éteindre la lampe") : Tr.t("Allumer la lampe"));
        applyRequest();
        Speaker.say(this, torch ? Tr.t("Lampe allumée") : Tr.t("Lampe éteinte"));
    }

    private void toggleFreeze() {
        if (!isFrozen) {
            Bitmap b = texture.getBitmap();
            if (b == null) return;
            frozen.setImageBitmap(b);
            frozenScale = 1f;
            frozen.setScaleX(1f); frozen.setScaleY(1f);
            frozen.setTranslationX(0); frozen.setTranslationY(0);
            frozen.setVisibility(View.VISIBLE);
            isFrozen = true;
            try { if (session != null) session.stopRepeating(); } catch (Exception ignored) {}
            freezeBtn.setText("▶");
            freezeBtn.setContentDescription(Tr.t("Reprendre l'image en direct"));
            Speaker.say(this, Tr.t("Image figée. Pince pour agrandir, glisse pour déplacer."));
        } else {
            isFrozen = false;
            frozen.setVisibility(View.GONE);
            freezeBtn.setText("❚❚");
            freezeBtn.setContentDescription(Tr.t("Figer l'image"));
            applyRequest();
            Speaker.say(this, Tr.t("Image en direct"));
        }
    }

    // ------------------------------------------------------------------ codes-barres (Open Food Facts)

    private TextView product;
    private boolean scanning;
    private String lastCode;
    private final Handler ui = new Handler(android.os.Looper.getMainLooper());

    private void toggleScan() {
        scanning = !scanning;
        if (scanning) {
            if (isFrozen) toggleFreeze();
            lastCode = null;
            product.setVisibility(View.GONE);
            Speaker.say(this, Tr.t("Vise le code-barres du produit, à une main de distance."));
            ui.postDelayed(scanTask, 600);
        } else {
            ui.removeCallbacks(scanTask);
            Speaker.say(this, Tr.t("Lecture des codes-barres arrêtée."));
        }
    }

    private final Runnable scanTask = new Runnable() {
        @Override public void run() {
            if (!scanning || bg == null) return;
            final Bitmap b = texture.getBitmap(Math.min(960, Math.max(1, texture.getWidth())),
                    Math.max(1, Math.round(texture.getHeight() * Math.min(960f, texture.getWidth()) / Math.max(1, texture.getWidth()))));
            if (b == null) { ui.postDelayed(this, 500); return; }
            bg.post(new Runnable() {
                @Override public void run() {
                    final String code = decode(b);
                    ui.post(new Runnable() {
                        @Override public void run() {
                            if (!scanning) return;
                            if (code != null && !code.equals(lastCode)) { lastCode = code; found(code); }
                            else ui.postDelayed(scanTask, 400);
                        }
                    });
                }
            });
        }
    };

    private static String decode(Bitmap b) {
        try {
            int w = b.getWidth(), h = b.getHeight();
            int[] px = new int[w * h];
            b.getPixels(px, 0, w, 0, 0, w, h);
            com.google.zxing.BinaryBitmap bb = new com.google.zxing.BinaryBitmap(new com.google.zxing.common.HybridBinarizer(
                    new com.google.zxing.RGBLuminanceSource(w, h, px)));
            java.util.Map<com.google.zxing.DecodeHintType, Object> hints = new java.util.EnumMap<com.google.zxing.DecodeHintType, Object>(com.google.zxing.DecodeHintType.class);
            hints.put(com.google.zxing.DecodeHintType.POSSIBLE_FORMATS, java.util.EnumSet.of(com.google.zxing.BarcodeFormat.EAN_13,
                    com.google.zxing.BarcodeFormat.EAN_8, com.google.zxing.BarcodeFormat.UPC_A, com.google.zxing.BarcodeFormat.UPC_E));
            hints.put(com.google.zxing.DecodeHintType.TRY_HARDER, Boolean.TRUE);
            return new com.google.zxing.MultiFormatReader().decode(bb, hints).getText();
        } catch (Exception e) {
            return null;
        }
    }

    private void found(final String code) {
        scanning = false;
        try { new android.media.ToneGenerator(android.media.AudioManager.STREAM_MUSIC, 80).startTone(android.media.ToneGenerator.TONE_PROP_BEEP, 150); } catch (Exception ignored) {}
        Ui.tick(stage);
        product.setText(Tr.t("Code ") + code + Tr.t(" : recherche du produit…"));
        product.setVisibility(View.VISIBLE);
        new Thread(new Runnable() {
            @Override public void run() {
                final String text = lookup(code);
                ui.post(new Runnable() {
                    @Override public void run() {
                        product.setText(text);
                        Speaker.say(MagnifierActivity.this, text, null);
                    }
                });
            }
        }, "produit").start();
    }

    private static final String[][] ALLERGENS = {{"gluten", "gluten"}, {"milk", "lait"}, {"eggs", Tr.t("œufs")}, {"nuts", Tr.t("fruits à coque")},
            {"peanuts", "arachides"}, {"soybeans", "soja"}, {"fish", "poisson"}, {"crustaceans", Tr.t("crustacés")}, {"celery", Tr.t("céleri")},
            {"mustard", "moutarde"}, {"sesame-seeds", Tr.t("sésame")}, {"sulphur-dioxide-and-sulphites", "sulfites"}, {"lupin", "lupin"},
            {"molluscs", "mollusques"}};

    /** Interroge la base libre Open Food Facts (seul le code-barres est envoyé). */
    static String lookup(String code) {
        java.net.HttpURLConnection c = null;
        try {
            c = (java.net.HttpURLConnection) new java.net.URL("https://world.openfoodfacts.org/api/v2/product/" + code
                    + ".json?fields=product_name_fr,product_name,brands,quantity,nutriscore_grade,allergens_tags,ingredients_text_fr").openConnection();
            c.setRequestProperty("User-Agent", "Lisys/1.8 (QMTech; Android)");
            c.setConnectTimeout(10000);
            c.setReadTimeout(10000);
            if (c.getResponseCode() == 404) return Tr.t("Produit inconnu (code ") + code + ").";
            java.io.InputStream in = c.getInputStream();
            String json;
            try { json = new String(Extractor.readStream(in, 2 * 1024 * 1024), "UTF-8"); } finally { in.close(); }
            org.json.JSONObject o = new org.json.JSONObject(json);
            if (o.optInt("status", 0) != 1) return Tr.t("Produit inconnu (code ") + code + ").";
            org.json.JSONObject p = o.getJSONObject("product");
            StringBuilder sb = new StringBuilder();
            String name = p.optString("product_name_fr", "");
            if (name.length() == 0) name = p.optString("product_name", "Produit sans nom");
            sb.append(name);
            if (p.optString("brands").length() > 0) sb.append(", ").append(p.optString("brands"));
            if (p.optString("quantity").length() > 0) sb.append(", ").append(p.optString("quantity"));
            sb.append(".");
            String ns = p.optString("nutriscore_grade", "");
            if (ns.matches("[a-e]")) sb.append(" Nutri-Score ").append(ns.toUpperCase(Locale.FRANCE)).append(".");
            org.json.JSONArray al = p.optJSONArray("allergens_tags");
            if (al != null && al.length() > 0) {
                List<String> names = new java.util.ArrayList<String>();
                for (int i = 0; i < al.length(); i++) {
                    String t = al.optString(i).replaceFirst("^[a-z]{2}:", "");
                    String fr = t;
                    for (String[] a : ALLERGENS) if (a[0].equals(t)) fr = a[1];
                    names.add(fr);
                }
                sb.append(Tr.t(" Allergènes : ")).append(android.text.TextUtils.join(", ", names)).append(".");
            } else {
                sb.append(Tr.t(" Aucun allergène indiqué."));
            }
            String ing = p.optString("ingredients_text_fr", "").replaceAll("[_*]", "");
            if (ing.length() > 0) sb.append(Tr.t(" Ingrédients : ")).append(ing.length() > 300 ? ing.substring(0, 300) + "…" : ing);
            return sb.toString();
        } catch (java.net.UnknownHostException e) {
            return Tr.t("Pas de connexion internet : impossible de chercher le produit (code ") + code + ").";
        } catch (Exception e) {
            return Tr.t("Recherche du produit impossible (code ") + code + ").";
        } finally {
            if (c != null) c.disconnect();
        }
    }

    /** Lit le texte de ce qui est affiché (image figée ou image en direct). */
    private void readText() {
        Bitmap b = isFrozen && frozen.getDrawable() instanceof android.graphics.drawable.BitmapDrawable
                ? ((android.graphics.drawable.BitmapDrawable) frozen.getDrawable()).getBitmap() : texture.getBitmap();
        if (b == null) return;
        try {
            File dir = new File(getCacheDir(), "ocr");
            dir.mkdirs();
            File f = new File(dir, "loupe.jpg");
            FileOutputStream os = new FileOutputStream(f);
            try { b.compress(Bitmap.CompressFormat.JPEG, 92, os); } finally { os.close(); }
            startActivity(new Intent(this, OcrActivity.class).putExtra(OcrActivity.EXTRA_MODE, OcrActivity.MODE_IMAGE)
                    .putExtra(OcrActivity.EXTRA_PATH, f.getAbsolutePath()));
        } catch (Exception e) {
            Toast.makeText(this, Tr.t("Impossible de lire l'image."), Toast.LENGTH_LONG).show();
        }
    }
}
