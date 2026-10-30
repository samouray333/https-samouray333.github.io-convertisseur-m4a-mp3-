package com.qmtech.calorys;

import android.content.Context;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.SequenceInputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.Enumeration;
import java.util.Vector;
import java.util.zip.GZIPInputStream;

/**
 * Catalogue hors ligne des produits de marque (Open Food Facts France) :
 * téléchargé une fois, vérifié (SHA-256 de chaque morceau et de la base), décompressé
 * en flux, puis interrogé en lecture seule via l'index plein texte FTS4.
 */
public class CatalogStore {
    public interface Listener { void onProgress(String state, double progress, String message); }

    private static final String PREFS = "catalog";
    private static final String COLS = "food.*";
    private final Context ctx;
    private SQLiteDatabase db;
    private volatile boolean installing = false;

    public CatalogStore(Context ctx) { this.ctx = ctx.getApplicationContext(); }

    private File dbFile() { return new File(ctx.getFilesDir(), "catalog.db"); }
    private SharedPreferences prefs() { return ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

    public synchronized String status() {
        try {
            JSONObject o = new JSONObject();
            boolean ready = dbFile().exists() && prefs().getString("version", null) != null;
            o.put("ready", ready);
            o.put("installing", installing);
            o.put("version", prefs().getString("version", ""));
            return o.toString();
        } catch (Exception e) { return "{}"; }
    }

    private synchronized SQLiteDatabase open() {
        if (db == null && dbFile().exists()) {
            db = SQLiteDatabase.openDatabase(dbFile().getPath(), null,
                    SQLiteDatabase.OPEN_READONLY | SQLiteDatabase.NO_LOCALIZED_COLLATORS);
        }
        return db;
    }

    public String search(String match, int limit) {
        SQLiteDatabase d = open();
        if (d == null) return "[]";
        Cursor c = null;
        try {
            c = d.rawQuery("SELECT " + COLS + " FROM fts JOIN food ON food.id = fts.docid WHERE fts MATCH ? ORDER BY fts.docid LIMIT " + Math.max(1, Math.min(limit, 100)),
                    new String[]{match});
            JSONArray out = new JSONArray();
            while (c.moveToNext()) out.put(row(c));
            return out.toString();
        } catch (Exception e) {
            return "[]";
        } finally { if (c != null) c.close(); }
    }

    public String barcode(String code) {
        SQLiteDatabase d = open();
        if (d == null) return null;
        Cursor c = null;
        try {
            c = d.rawQuery("SELECT " + COLS + " FROM food WHERE code = ? LIMIT 1", new String[]{code});
            return c.moveToNext() ? row(c).toString() : null;
        } catch (Exception e) {
            return null;
        } finally { if (c != null) c.close(); }
    }

    private static JSONObject row(Cursor c) throws Exception {
        JSONObject o = new JSONObject();
        String[] names = c.getColumnNames();
        for (int i = 0; i < names.length; i++) {
            if (c.isNull(i)) continue;
            int t = c.getType(i);
            if (t == Cursor.FIELD_TYPE_FLOAT || t == Cursor.FIELD_TYPE_INTEGER) o.put(names[i], c.getDouble(i));
            else o.put(names[i], c.getString(i));
        }
        return o;
    }

    public synchronized void remove() {
        if (db != null) { db.close(); db = null; }
        dbFile().delete();
        prefs().edit().remove("version").apply();
    }

    /** Installation en tâche de fond. */
    public void install(final String manifestJson, final String sourcesJson, final Listener l) {
        if (installing) return;
        installing = true;
        new Thread(new Runnable() {
            @Override
            public void run() {
                File dir = new File(ctx.getFilesDir(), "catalog-dl");
                try {
                    JSONObject m = new JSONObject(manifestJson);
                    JSONArray sources = new JSONArray(sourcesJson);
                    JSONArray parts = m.getJSONArray("parts");
                    long gzSize = m.getLong("gzSize"), dbSize = m.getLong("dbSize");
                    long free = ctx.getFilesDir().getUsableSpace();
                    if (free < gzSize + dbSize + 30L * 1024 * 1024) {
                        throw new Exception("espace insuffisant : il faut " + ((gzSize + dbSize) / 1048576 + 30) + " Mo libres");
                    }
                    if (!dir.exists() && !dir.mkdirs()) throw new Exception("dossier inaccessible");
                    long done = 0;
                    Vector<InputStream> streams = new Vector<>();
                    for (int i = 0; i < parts.length(); i++) {
                        JSONObject p = parts.getJSONObject(i);
                        File f = new File(dir, p.getString("name"));
                        if (!(f.exists() && f.length() == p.getLong("size") && sha256(f).equals(p.getString("sha256")))) {
                            download(sources, p, f, done, gzSize, l);
                        }
                        done += p.getLong("size");
                        streams.add(new BufferedInputStream(new FileInputStream(f), 1 << 16));
                    }
                    l.onProgress("progress", 0.9, "Décompression…");
                    File tmp = new File(ctx.getFilesDir(), "catalog.db.tmp");
                    MessageDigest md = MessageDigest.getInstance("SHA-256");
                    final Enumeration<InputStream> en = streams.elements();
                    InputStream in = new GZIPInputStream(new SequenceInputStream(en), 1 << 16);
                    OutputStream os = new FileOutputStream(tmp);
                    long written = 0;
                    try {
                        byte[] buf = new byte[1 << 16];
                        int n;
                        while ((n = in.read(buf)) > 0) {
                            os.write(buf, 0, n); md.update(buf, 0, n); written += n;
                            if ((written & ((1 << 23) - 1)) < n) l.onProgress("progress", 0.9 + 0.09 * written / dbSize, "Décompression…");
                        }
                    } finally { in.close(); os.close(); }
                    if (written != dbSize || !hex(md.digest()).equals(m.getString("dbSha256"))) {
                        tmp.delete();
                        throw new Exception("catalogue corrompu, réessaie");
                    }
                    synchronized (CatalogStore.this) {
                        if (db != null) { db.close(); db = null; }
                        File target = dbFile();
                        target.delete();
                        if (!tmp.renameTo(target)) throw new Exception("enregistrement impossible");
                        prefs().edit().putString("version", m.getString("version")).apply();
                    }
                    deleteDir(dir);
                    installing = false;
                    l.onProgress("ready", 1, "");
                } catch (Exception e) {
                    installing = false;
                    l.onProgress("error", 0, e.getMessage() == null ? e.toString() : e.getMessage());
                }
            }
        }).start();
    }

    private void download(JSONArray sources, JSONObject p, File f, long before, long total, Listener l) throws Exception {
        Exception last = null;
        for (int s = 0; s < sources.length(); s++) {
            HttpURLConnection c = null;
            try {
                URL u = new URL(sources.getString(s) + p.getString("name"));
                c = (HttpURLConnection) u.openConnection();
                c.setConnectTimeout(20000);
                c.setReadTimeout(30000);
                c.setRequestProperty("User-Agent", "Calorys/1.4 (QMTech; Android)");
                if (c.getResponseCode() != 200) { last = new Exception("HTTP " + c.getResponseCode()); continue; }
                MessageDigest md = MessageDigest.getInstance("SHA-256");
                InputStream in = new BufferedInputStream(c.getInputStream(), 1 << 16);
                OutputStream os = new FileOutputStream(f);
                long got = 0;
                try {
                    byte[] buf = new byte[1 << 16];
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        os.write(buf, 0, n); md.update(buf, 0, n); got += n;
                        if ((got & ((1 << 20) - 1)) < n) l.onProgress("progress", 0.9 * (before + got) / total, "Téléchargement…");
                    }
                } finally { in.close(); os.close(); }
                if (got != p.getLong("size") || !hex(md.digest()).equals(p.getString("sha256"))) {
                    f.delete();
                    last = new Exception("fichier altéré pendant le téléchargement");
                    continue;
                }
                return;
            } catch (Exception e) {
                last = e;
            } finally { if (c != null) c.disconnect(); }
        }
        throw last != null ? new Exception("téléchargement impossible (" + last.getMessage() + ")") : new Exception("téléchargement impossible");
    }

    static String sha256(File f) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        InputStream in = new FileInputStream(f);
        try {
            byte[] buf = new byte[1 << 16];
            int n;
            while ((n = in.read(buf)) > 0) md.update(buf, 0, n);
        } finally { in.close(); }
        return hex(md.digest());
    }

    static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    static void deleteDir(File d) {
        File[] fs = d.listFiles();
        if (fs != null) for (File f : fs) f.delete();
        d.delete();
    }
}
