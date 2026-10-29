package com.echomatras.lisys;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.provider.MediaStore;
import android.text.format.DateFormat;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

/**
 * Lire le papier : photo d'un courrier, d'une notice, d'une boîte de médicament…
 * ou image / PDF scanné. Le texte est reconnu sur le téléphone, puis lu à voix haute.
 */
public class OcrActivity extends Activity {

    public static final String EXTRA_MODE = "mode";
    public static final String MODE_CAMERA = "camera";
    public static final String MODE_GALLERY = "gallery";
    public static final String MODE_IMAGE = "image";
    public static final String MODE_PDF = "pdf";

    private static final int REQ_CAMERA = 1;
    private static final int REQ_GALLERY = 2;

    private final Handler main = new Handler(Looper.getMainLooper());
    private OcrEngine engine;
    private Ui.Palette pal;
    private ImageView preview;
    private TextView status;
    private ProgressBar bar;
    private LinearLayout actions;
    private boolean working;
    private boolean cancelled;

    // PDF scanné
    private PdfRenderer renderer;
    private ParcelFileDescriptor pdfFd;
    private String pdfTitle;
    private final List<String> pdfParas = new ArrayList<String>();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        pal = Ui.palette(this);
        Ui.systemBars(this, pal);
        int pad = Ui.dp(this, 16);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);
        root.setPadding(pad, pad, pad, pad);

        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);
        TextView back = Ui.roundButton(this, "←", "Retour", pal.surface, pal.text, 48);
        back.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { finish(); } });
        head.addView(back);
        TextView title = Ui.label(this, "Lire une photo", 24, pal.text, true);
        title.setPadding(Ui.dp(this, 8), 0, 0, 0);
        head.addView(title);
        root.addView(head);

        preview = new ImageView(this);
        preview.setScaleType(ImageView.ScaleType.FIT_CENTER);
        preview.setContentDescription("Aperçu de la photo");
        LinearLayout.LayoutParams plp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1);
        plp.setMargins(0, pad, 0, pad);
        root.addView(preview, plp);

        status = Ui.label(this, "Prends en photo un courrier, une notice, une étiquette… "
                + "bien à plat, avec de la lumière, en remplissant l'écran.", 20, pal.text, true);
        status.setGravity(Gravity.CENTER);
        root.addView(status);
        bar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        bar.setMax(100);
        bar.setVisibility(View.INVISIBLE);
        LinearLayout.LayoutParams blp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 14));
        blp.setMargins(0, Ui.dp(this, 10), 0, Ui.dp(this, 10));
        root.addView(bar, blp);

        actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.VERTICAL);
        Button photo = Ui.bigButton(this, "📷   Prendre une photo", pal.button, pal.buttonText);
        photo.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { takePhoto(); } });
        actions.addView(photo, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        View sp = new View(this);
        actions.addView(sp, new LinearLayout.LayoutParams(1, Ui.dp(this, 10)));
        Button gallery = Ui.bigButton(this, "🖼   Choisir une image", pal.surface, pal.text);
        gallery.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { pickImage(); } });
        actions.addView(gallery, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(actions);

        setContentView(root);
        engine = new OcrEngine(this, root);

        if (state == null) {
            String mode = getIntent().getStringExtra(EXTRA_MODE);
            Uri data = getIntent().getData();
            if (MODE_CAMERA.equals(mode)) takePhoto();
            else if (MODE_GALLERY.equals(mode)) pickImage();
            else if (MODE_PDF.equals(mode) && data != null) processPdf(data);
            else if (data != null) processImage(data);
        }
    }

    @Override
    protected void onDestroy() {
        cancelled = true;
        closePdf();
        engine.destroy();
        super.onDestroy();
    }

    // ------------------------------------------------------------------ choix de l'image

    private void takePhoto() {
        if (working) return;
        PhotoProvider.photoFile(this).delete();
        Uri out = PhotoProvider.photoUri();
        Intent i = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        i.putExtra(MediaStore.EXTRA_OUTPUT, out);
        i.setClipData(ClipData.newRawUri("photo", out));
        i.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try {
            startActivityForResult(i, REQ_CAMERA);
        } catch (Exception e) {
            Toast.makeText(this, "Aucune appli Appareil photo trouvée.", Toast.LENGTH_LONG).show();
        }
    }

    private void pickImage() {
        if (working) return;
        Intent i = new Intent(Intent.ACTION_GET_CONTENT);
        i.setType("image/*");
        i.addCategory(Intent.CATEGORY_OPENABLE);
        try {
            startActivityForResult(Intent.createChooser(i, "Choisir une image"), REQ_GALLERY);
        } catch (Exception e) {
            Toast.makeText(this, "Aucune galerie trouvée.", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (res != RESULT_OK) return;
        if (req == REQ_CAMERA) {
            if (PhotoProvider.photoFile(this).length() > 0) processImage(PhotoProvider.photoUri());
            else if (data != null && data.getData() != null) processImage(data.getData());
            else Toast.makeText(this, "La photo n'a pas été enregistrée, réessaie.", Toast.LENGTH_LONG).show();
        } else if (req == REQ_GALLERY && data != null && data.getData() != null) {
            processImage(data.getData());
        }
    }

    // ------------------------------------------------------------------ photo / image

    private void setWorking(boolean w, String message) {
        working = w;
        status.setText(message);
        bar.setVisibility(w ? View.VISIBLE : View.INVISIBLE);
        if (w) bar.setProgress(0);
        actions.setVisibility(w ? View.GONE : View.VISIBLE);
    }

    private void processImage(final Uri uri) {
        setWorking(true, "Préparation de l'image…");
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    final File f = OcrEngine.prepare(OcrActivity.this, uri, "image.jpg");
                    BitmapFactory.Options o = new BitmapFactory.Options();
                    o.inSampleSize = 4;
                    final Bitmap small = BitmapFactory.decodeFile(f.getAbsolutePath(), o);
                    main.post(new Runnable() { @Override public void run() {
                        if (cancelled) return;
                        preview.setImageBitmap(small);
                        recognizeImage(f);
                    } });
                } catch (final Exception e) {
                    main.post(new Runnable() { @Override public void run() {
                        setWorking(false, e instanceof Extractor.UserError ? e.getMessage() : "Impossible d'ouvrir cette image.");
                    } });
                }
            }
        }, "ocr-prep").start();
    }

    private void recognizeImage(File f) {
        status.setText("Lecture du texte de la photo…");
        engine.recognize(f, new OcrEngine.Callback() {
            @Override public void onProgress(int p) {
                bar.setProgress(p);
                status.setText("Lecture du texte de la photo… " + p + " %");
            }
            @Override public void onDone(String text) {
                List<String> paras = Extractor.ocrParagraphs(text);
                if (Extractor.countChars(paras) < 3) {
                    setWorking(false, "Je n'ai pas trouvé de texte. Reprends la photo plus près, bien à plat, "
                            + "avec de la lumière et sans reflet.");
                    return;
                }
                String first = paras.get(0);
                String title = first.length() > 60 ? first.substring(0, 57) + "…" : first;
                openReader(title, paras, "photo:" + System.currentTimeMillis());
            }
            @Override public void onError(String message) { setWorking(false, message); }
        });
    }

    private void openReader(String title, List<String> paras, String source) {
        Extractor.Result r = new Extractor.Result();
        r.kind = "PHOTO";
        r.title = title;
        r.paragraphs.addAll(paras);
        r = Extractor.finish(r);
        Library.Entry e = Library.add(this, r, source);
        Intent i = new Intent(this, ReaderActivity.class);
        i.putExtra(ReaderActivity.EXTRA_ID, e.id);
        i.putExtra(ReaderActivity.EXTRA_AUTOPLAY, true);
        startActivity(i);
        finish();
    }

    // ------------------------------------------------------------------ PDF scanné

    private void processPdf(final Uri uri) {
        setWorking(true, "Ouverture du PDF…");
        pdfTitle = Extractor.stripExtension(Extractor.displayName(this, uri));
        new Thread(new Runnable() {
            @Override public void run() {
                try {
                    File f = new File(getCacheDir(), "ocr/scan.pdf");
                    f.getParentFile().mkdirs();
                    InputStream in = getContentResolver().openInputStream(uri);
                    if (in == null) throw new Exception();
                    try { Extractor.copy(in, f, Extractor.MAX_FILE); } finally { in.close(); }
                    pdfFd = ParcelFileDescriptor.open(f, ParcelFileDescriptor.MODE_READ_ONLY);
                    renderer = new PdfRenderer(pdfFd);
                    main.post(new Runnable() { @Override public void run() { pdfPage(0); } });
                } catch (Exception e) {
                    main.post(new Runnable() { @Override public void run() {
                        setWorking(false, "Impossible d'ouvrir ce PDF (il est peut-être protégé par un mot de passe).");
                    } });
                }
            }
        }, "ocr-pdf").start();
    }

    private void pdfPage(final int index) {
        if (cancelled || renderer == null) return;
        final int count = renderer.getPageCount();
        if (index >= count) {
            closePdf();
            if (Extractor.countChars(pdfParas) < 3) {
                setWorking(false, "Je n'ai pas trouvé de texte dans ce PDF.");
                return;
            }
            openReader(pdfTitle, pdfParas, "pdf-ocr:" + pdfTitle + ":" + count);
            return;
        }
        status.setText("Page " + (index + 1) + " / " + count + " : préparation…");
        new Thread(new Runnable() {
            @Override public void run() {
                File out = new File(getCacheDir(), "ocr/page.jpg");
                Bitmap small = null;
                try {
                    synchronized (OcrActivity.this) {
                        PdfRenderer.Page page = renderer.openPage(index);
                        float scale = 2000f / Math.max(1, page.getWidth());
                        int w = Math.round(page.getWidth() * scale), h = Math.round(page.getHeight() * scale);
                        if (h > 3200) { w = w * 3200 / h; h = 3200; }
                        Bitmap bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
                        bmp.eraseColor(Color.WHITE);
                        page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
                        page.close();
                        small = Bitmap.createScaledBitmap(bmp, Math.max(1, w / 4), Math.max(1, h / 4), true);
                        OcrEngine.save(bmp, 0, out);
                    }
                } catch (Exception e) {
                    out = null;
                }
                final File f = out;
                final Bitmap pv = small;
                main.post(new Runnable() { @Override public void run() {
                    if (cancelled) return;
                    if (pv != null) preview.setImageBitmap(pv);
                    if (f == null) { pdfPage(index + 1); return; }
                    engine.recognize(f, new OcrEngine.Callback() {
                        @Override public void onProgress(int p) {
                            int total = (index * 100 + p) / count;
                            bar.setProgress(total);
                            status.setText("Lecture de la page " + (index + 1) + " / " + count + " … " + p + " %");
                        }
                        @Override public void onDone(String text) {
                            pdfParas.addAll(Extractor.ocrParagraphs(text));
                            pdfPage(index + 1);
                        }
                        @Override public void onError(String message) {
                            closePdf();
                            setWorking(false, message);
                        }
                    });
                } });
            }
        }, "ocr-page").start();
    }

    private synchronized void closePdf() {
        try { if (renderer != null) renderer.close(); } catch (Exception ignored) {}
        try { if (pdfFd != null) pdfFd.close(); } catch (Exception ignored) {}
        renderer = null;
        pdfFd = null;
    }

    static String defaultTitle(Activity a) {
        return "Photo du " + DateFormat.getDateFormat(a).format(new Date());
    }
}
