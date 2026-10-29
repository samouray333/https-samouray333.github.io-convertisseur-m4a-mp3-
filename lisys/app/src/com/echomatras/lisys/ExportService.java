package com.echomatras.lisys;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ContentResolver;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.MediaScannerConnection;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.MediaStore;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.widget.Toast;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Transforme un document entier en fichier audio .m4a (livre audio), enregistré dans
 * Téléchargements/Lisys. Tourne en arrière-plan avec une notification de progression.
 */
public class ExportService extends Service {

    public static final String EXTRA_ID = "id";
    public static final String ACTION_CANCEL = "com.echomatras.lisys.EXPORT_CANCEL";
    private static final String CHANNEL = "export";
    private static final int NOTIF_ID = 2;
    private static final int NOTIF_DONE = 3;

    private static volatile boolean running;
    private volatile boolean cancelled;
    private final Handler main = new Handler(Looper.getMainLooper());

    public static boolean isRunning() { return running; }

    @Override
    public IBinder onBind(Intent intent) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_CANCEL.equals(intent.getAction())) {
            cancelled = true;
            return START_NOT_STICKY;
        }
        final String id = intent == null ? null : intent.getStringExtra(EXTRA_ID);
        if (id == null) { stopSelf(); return START_NOT_STICKY; }
        if (running) {
            Toast.makeText(this, "Un export audio est déjà en cours.", Toast.LENGTH_SHORT).show();
            return START_NOT_STICKY;
        }
        running = true;
        cancelled = false;
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Export audio", NotificationManager.IMPORTANCE_LOW));
        Notification n = progressNotification("Préparation…", 0, 0);
        if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
        else startForeground(NOTIF_ID, n);
        new Thread(new Runnable() {
            @Override public void run() { export(id); }
        }, "export-audio").start();
        return START_NOT_STICKY;
    }

    private Notification progressNotification(String text, int done, int total) {
        PendingIntent cancel = PendingIntent.getService(this, 10,
                new Intent(this, ExportService.class).setAction(ACTION_CANCEL),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_notif)
                .setContentTitle("Création du fichier audio")
                .setContentText(text)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .addAction(new Notification.Action.Builder(null, "Annuler", cancel).build());
        if (total > 0) b.setProgress(total, done, false);
        else b.setProgress(0, 0, true);
        return b.build();
    }

    private void progress(String text, int done, int total) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        try { nm.notify(NOTIF_ID, progressNotification(text, done, total)); } catch (Exception ignored) {}
    }

    private void export(String id) {
        TextToSpeech tts = null;
        AacEncoder enc = null;
        File out = new File(getCacheDir(), "export.m4a");
        String error = null;
        Uri saved = null;
        Library.Entry entry = Library.get(this, id);
        String title = entry != null ? entry.title : "Lisys";
        try {
            List<String> paras = Library.loadParagraphs(this, id);
            if (paras.isEmpty()) throw new Exception("Document vide.");

            final CountDownLatch init = new CountDownLatch(1);
            final int[] status = {TextToSpeech.ERROR};
            tts = new TextToSpeech(getApplicationContext(), new TextToSpeech.OnInitListener() {
                @Override public void onInit(int s) { status[0] = s; init.countDown(); }
            });
            if (!init.await(30, TimeUnit.SECONDS) || status[0] != TextToSpeech.SUCCESS) {
                throw new Exception("Moteur de synthèse vocale indisponible.");
            }
            ReaderService.applyVoice(this, tts);
            tts.setSpeechRate(Prefs.rate(this));
            tts.setPitch(Prefs.pitch(this));

            final Object lock = new Object();
            final String[] doneId = {null};
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String u) {}
                @Override public void onDone(String u) { signal(u); }
                @Override public void onError(String u) { signal("ERR"); }
                @Override public void onError(String u, int code) { signal("ERR"); }
                private void signal(String u) {
                    synchronized (lock) { doneId[0] = u; lock.notifyAll(); }
                }
            });

            List<String> chunks = chunk(paras, Math.min(3000, TextToSpeech.getMaxSpeechInputLength() - 200));
            File wav = new File(getCacheDir(), "export_part.wav");
            for (int i = 0; i < chunks.size(); i++) {
                if (cancelled) throw new InterruptedException();
                progress("Partie " + (i + 1) + " / " + chunks.size(), i, chunks.size());
                String uid = "part" + i;
                synchronized (lock) { doneId[0] = null; }
                int r = tts.synthesizeToFile(chunks.get(i), new Bundle(), wav, uid);
                if (r != TextToSpeech.SUCCESS) throw new Exception("La synthèse vocale a échoué.");
                long deadline = System.currentTimeMillis() + 180000;
                synchronized (lock) {
                    while (doneId[0] == null && !cancelled) {
                        long left = deadline - System.currentTimeMillis();
                        if (left <= 0) throw new Exception("La synthèse vocale ne répond plus.");
                        lock.wait(Math.min(left, 1000));
                    }
                    if (cancelled) throw new InterruptedException();
                    if ("ERR".equals(doneId[0])) throw new Exception("La synthèse vocale a échoué (partie " + (i + 1) + ").");
                }
                enc = appendWav(wav, enc, out);
                if (enc != null) enc.silence(400);
                wav.delete();
            }
            if (enc == null) throw new Exception("Aucun son n'a été produit.");
            progress("Finalisation…", chunks.size(), chunks.size());
            enc.finish();
            enc = null;
            saved = publish(out, safeName(title) + ".m4a");
        } catch (InterruptedException e) {
            error = "Export annulé.";
        } catch (Exception e) {
            error = e.getMessage() != null ? e.getMessage() : "Erreur pendant l'export.";
        } finally {
            if (enc != null) enc.release();
            if (tts != null) tts.shutdown();
            out.delete();
            running = false;
        }
        finishNotification(title, saved, error);
        stopForeground(Service.STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    /** Regroupe les paragraphes en morceaux de taille raisonnable pour le moteur vocal. */
    static List<String> chunk(List<String> paras, int max) {
        List<String> out = new ArrayList<String>();
        StringBuilder sb = new StringBuilder();
        for (String p : paras) {
            List<String> pieces = new ArrayList<String>();
            if (p.length() > max) pieces.addAll(Sentences.split(p));
            else pieces.add(p);
            for (String s : pieces) {
                if (sb.length() + s.length() + 2 > max && sb.length() > 0) {
                    out.add(sb.toString());
                    sb.setLength(0);
                }
                sb.append(s).append(s == pieces.get(pieces.size() - 1) ? "\n\n" : " ");
            }
        }
        if (sb.toString().trim().length() > 0) out.add(sb.toString());
        return out;
    }

    /** Lit un fichier WAV produit par le moteur vocal et l'ajoute au fichier AAC. */
    private AacEncoder appendWav(File wav, AacEncoder enc, File out) throws Exception {
        InputStream in = new BufferedInputStream(new FileInputStream(wav), 65536);
        try {
            byte[] h = new byte[12];
            if (readFully(in, h, 12) < 12 || h[0] != 'R' || h[8] != 'W') return enc;
            int rate = 0, channels = 1, bits = 16;
            byte[] ch = new byte[8];
            while (readFully(in, ch, 8) == 8) {
                String cid = new String(ch, 0, 4, "US-ASCII");
                long size = (ch[4] & 0xFFL) | (ch[5] & 0xFFL) << 8 | (ch[6] & 0xFFL) << 16 | (ch[7] & 0xFFL) << 24;
                if (cid.equals("fmt ")) {
                    byte[] f = new byte[(int) size];
                    readFully(in, f, f.length);
                    channels = (f[2] & 0xFF) | (f[3] & 0xFF) << 8;
                    rate = (f[4] & 0xFF) | (f[5] & 0xFF) << 8 | (f[6] & 0xFF) << 16 | (f[7] & 0xFF) << 24;
                    bits = (f[14] & 0xFF) | (f[15] & 0xFF) << 8;
                } else if (cid.equals("data")) {
                    if (rate <= 0 || bits != 16) throw new Exception("Format audio du moteur vocal non pris en charge.");
                    if (enc == null) enc = new AacEncoder(out, rate);
                    streamPcm(in, size, channels, rate, enc);
                    return enc;
                } else {
                    long skipped = 0;
                    while (skipped < size) {
                        long k = in.skip(size - skipped);
                        if (k <= 0) break;
                        skipped += k;
                    }
                }
            }
            return enc;
        } finally {
            in.close();
        }
    }

    /** Convertit en mono et à la fréquence de l'encodeur si besoin, puis encode par blocs. */
    private void streamPcm(InputStream in, long size, int channels, int rate, AacEncoder enc) throws Exception {
        byte[] buf = new byte[channels * 2 * 4096];
        long left = size == 0 || size == 0xFFFFFFFFL ? Long.MAX_VALUE : size;
        int dst = enc.sampleRate();
        double pos = 0;
        double step = (double) rate / dst;
        short prev = 0;
        while (left > 0) {
            int want = (int) Math.min(buf.length, left);
            int n = readFully(in, buf, want);
            if (n <= 0) break;
            left -= n;
            int frames = n / (channels * 2);
            short[] mono = new short[frames];
            for (int f = 0; f < frames; f++) {
                int sum = 0;
                for (int c = 0; c < channels; c++) {
                    int o = (f * channels + c) * 2;
                    sum += (short) ((buf[o] & 0xFF) | (buf[o + 1] << 8));
                }
                mono[f] = (short) (sum / channels);
            }
            if (rate == dst) {
                byte[] b = new byte[frames * 2];
                for (int f = 0; f < frames; f++) { b[2 * f] = (byte) mono[f]; b[2 * f + 1] = (byte) (mono[f] >> 8); }
                enc.write(b, 0, b.length);
            } else {
                // Rééchantillonnage linéaire simple (rare : seulement si la voix change de fréquence).
                List<Short> res = new ArrayList<Short>();
                while (pos < frames) {
                    int i0 = (int) pos;
                    double t = pos - i0;
                    short a = i0 == 0 ? prev : mono[i0 - 1];
                    short b2 = mono[i0];
                    res.add((short) (a + (b2 - a) * t));
                    pos += step;
                }
                pos -= frames;
                if (frames > 0) prev = mono[frames - 1];
                byte[] b = new byte[res.size() * 2];
                for (int f = 0; f < res.size(); f++) { short v = res.get(f); b[2 * f] = (byte) v; b[2 * f + 1] = (byte) (v >> 8); }
                enc.write(b, 0, b.length);
            }
        }
    }

    private static int readFully(InputStream in, byte[] b, int len) throws Exception {
        int off = 0;
        while (off < len) {
            int n = in.read(b, off, len - off);
            if (n < 0) break;
            off += n;
        }
        return off;
    }

    static String safeName(String t) {
        String s = t.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", " ").replaceAll("\\s+", " ").trim();
        if (s.length() > 80) s = s.substring(0, 80).trim();
        return s.length() == 0 ? "Lisys" : s;
    }

    /** Copie le fichier dans Téléchargements/Lisys et renvoie son adresse pour le partage. */
    private Uri publish(File src, String name) throws Exception {
        if (Build.VERSION.SDK_INT >= 29) {
            ContentResolver cr = getContentResolver();
            ContentValues v = new ContentValues();
            v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
            v.put(MediaStore.MediaColumns.MIME_TYPE, "audio/mp4");
            v.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Lisys");
            v.put(MediaStore.MediaColumns.IS_PENDING, 1);
            Uri uri = cr.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
            if (uri == null) throw new Exception("Impossible d'enregistrer le fichier.");
            OutputStream os = cr.openOutputStream(uri);
            InputStream in = new FileInputStream(src);
            try {
                byte[] buf = new byte[65536];
                int n;
                while ((n = in.read(buf)) > 0) os.write(buf, 0, n);
            } finally {
                in.close();
                os.close();
            }
            v.clear();
            v.put(MediaStore.MediaColumns.IS_PENDING, 0);
            cr.update(uri, v, null, null);
            return uri;
        }
        File dir = new File(Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS), "Lisys");
        dir.mkdirs();
        File dst = new File(dir, name);
        int k = 2;
        while (dst.exists()) dst = new File(dir, name.replace(".m4a", " (" + (k++) + ").m4a"));
        InputStream in = new FileInputStream(src);
        try {
            Extractor.copy(in, dst, Long.MAX_VALUE);
        } finally {
            in.close();
        }
        final CountDownLatch l = new CountDownLatch(1);
        final Uri[] res = {null};
        MediaScannerConnection.scanFile(this, new String[]{dst.getAbsolutePath()}, new String[]{"audio/mp4"},
                new MediaScannerConnection.OnScanCompletedListener() {
                    @Override public void onScanCompleted(String path, Uri uri) { res[0] = uri; l.countDown(); }
                });
        l.await(10, TimeUnit.SECONDS);
        return res[0];
    }

    private void finishNotification(final String title, Uri saved, final String error) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        Notification.Builder b = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_notif)
                .setAutoCancel(true);
        if (error != null) {
            b.setContentTitle("Export audio interrompu").setContentText(error);
        } else {
            b.setContentTitle("Fichier audio prêt")
                    .setContentText("Téléchargements/Lisys : " + safeName(title) + ".m4a");
            if (saved != null) {
                Intent play = new Intent(Intent.ACTION_VIEW).setDataAndType(saved, "audio/mp4")
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                b.setContentIntent(PendingIntent.getActivity(this, 20, Intent.createChooser(play, "Écouter avec"),
                        PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
                Intent share = new Intent(Intent.ACTION_SEND).setType("audio/mp4")
                        .putExtra(Intent.EXTRA_STREAM, saved)
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                b.addAction(new Notification.Action.Builder(null, "Partager",
                        PendingIntent.getActivity(this, 21, Intent.createChooser(share, "Partager le fichier audio"),
                                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT)).build());
            }
        }
        try { nm.notify(NOTIF_DONE, b.build()); } catch (Exception ignored) {}
        main.post(new Runnable() {
            @Override public void run() {
                Toast.makeText(ExportService.this, error != null ? error
                        : "Fichier audio enregistré dans Téléchargements/Lisys", Toast.LENGTH_LONG).show();
            }
        });
    }
}
