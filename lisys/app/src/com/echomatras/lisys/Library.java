package com.echomatras.lisys;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.Writer;
import java.nio.charset.Charset;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

/**
 * Bibliothèque locale : chaque document lu est gardé (texte extrait + position de lecture)
 * pour pouvoir reprendre là où on s'était arrêté.
 */
public final class Library {
    private Library() {}

    private static final Charset UTF8 = Charset.forName("UTF-8");
    private static final int MAX_ENTRIES = 60;

    public static final class Entry {
        public String id;
        public String title;
        public String source;   // uri du fichier, adresse web ou "texte"
        public String kind;     // PDF, DOCX, WEB, TEXTE...
        public int para;        // paragraphe en cours
        public int sentence;    // phrase en cours dans le paragraphe
        public int paraCount;
        public long opened;

        JSONObject toJson() throws Exception {
            JSONObject o = new JSONObject();
            o.put("id", id); o.put("title", title); o.put("source", source); o.put("kind", kind);
            o.put("para", para); o.put("sentence", sentence); o.put("paraCount", paraCount);
            o.put("opened", opened);
            return o;
        }

        static Entry fromJson(JSONObject o) {
            Entry e = new Entry();
            e.id = o.optString("id"); e.title = o.optString("title"); e.source = o.optString("source");
            e.kind = o.optString("kind"); e.para = o.optInt("para"); e.sentence = o.optInt("sentence");
            e.paraCount = o.optInt("paraCount"); e.opened = o.optLong("opened");
            return e;
        }

        public int percent() {
            if (paraCount <= 1) return para > 0 ? 100 : 0;
            return Math.min(100, Math.round(100f * para / (paraCount - 1)));
        }
    }

    private static File dir(Context c) {
        File d = new File(c.getFilesDir(), "docs");
        if (!d.exists()) d.mkdirs();
        return d;
    }

    private static File indexFile(Context c) { return new File(c.getFilesDir(), "bibliotheque.json"); }

    public static String makeId(String source, String title) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-1");
            byte[] h = md.digest((source + "|" + title).getBytes(UTF8));
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < 10; i++) sb.append(String.format("%02x", h[i]));
            return sb.toString();
        } catch (Exception e) {
            return Long.toHexString(System.nanoTime());
        }
    }

    public static synchronized List<Entry> list(Context c) {
        List<Entry> out = new ArrayList<Entry>();
        File f = indexFile(c);
        if (!f.exists()) return out;
        try {
            JSONArray a = new JSONArray(readAll(f));
            for (int i = 0; i < a.length(); i++) out.add(Entry.fromJson(a.getJSONObject(i)));
        } catch (Exception ignored) {
        }
        return out;
    }

    private static void saveList(Context c, List<Entry> list) {
        try {
            JSONArray a = new JSONArray();
            for (Entry e : list) a.put(e.toJson());
            File tmp = new File(c.getFilesDir(), "bibliotheque.json.tmp");
            writeAll(tmp, a.toString());
            tmp.renameTo(indexFile(c));
        } catch (Exception ignored) {
        }
    }

    public static synchronized Entry get(Context c, String id) {
        for (Entry e : list(c)) if (e.id.equals(id)) return e;
        return null;
    }

    /** Enregistre un document extrait. Si on l'a déjà lu, on garde la position de lecture. */
    public static synchronized Entry add(Context c, Extractor.Result r, String source) {
        String id = makeId(source, r.title);
        List<Entry> list = list(c);
        Entry existing = null;
        for (Entry e : list) if (e.id.equals(id)) existing = e;
        if (existing != null) list.remove(existing);
        Entry e = existing != null ? existing : new Entry();
        e.id = id;
        e.title = r.title;
        e.source = source;
        e.kind = r.kind;
        if (existing == null || existing.paraCount != r.paragraphs.size()) {
            e.para = 0;
            e.sentence = 0;
        }
        e.paraCount = r.paragraphs.size();
        e.opened = System.currentTimeMillis();
        list.add(0, e);
        while (list.size() > MAX_ENTRIES) {
            Entry old = list.remove(list.size() - 1);
            new File(dir(c), old.id + ".txt").delete();
        }
        StringBuilder sb = new StringBuilder();
        for (String p : r.paragraphs) sb.append(p.replace('\n', ' ')).append('\n');
        try {
            writeAll(new File(dir(c), id + ".txt"), sb.toString());
        } catch (Exception ignored) {
        }
        saveList(c, list);
        return e;
    }

    public static synchronized void touch(Context c, String id) {
        List<Entry> list = list(c);
        for (int i = 0; i < list.size(); i++) {
            Entry e = list.get(i);
            if (e.id.equals(id)) {
                e.opened = System.currentTimeMillis();
                list.remove(i);
                list.add(0, e);
                saveList(c, list);
                return;
            }
        }
    }

    public static synchronized void savePosition(Context c, String id, int para, int sentence) {
        List<Entry> list = list(c);
        for (Entry e : list) {
            if (e.id.equals(id)) {
                if (e.para == para && e.sentence == sentence) return;
                e.para = para;
                e.sentence = sentence;
                saveList(c, list);
                return;
            }
        }
    }

    public static synchronized void remove(Context c, String id) {
        List<Entry> list = list(c);
        for (int i = 0; i < list.size(); i++) {
            if (list.get(i).id.equals(id)) {
                list.remove(i);
                break;
            }
        }
        new File(dir(c), id + ".txt").delete();
        saveList(c, list);
    }

    public static synchronized void clear(Context c) {
        for (Entry e : list(c)) new File(dir(c), e.id + ".txt").delete();
        saveList(c, new ArrayList<Entry>());
    }

    public static List<String> loadParagraphs(Context c, String id) {
        List<String> out = new ArrayList<String>();
        File f = new File(dir(c), id + ".txt");
        if (!f.exists()) return out;
        BufferedReader br = null;
        try {
            br = new BufferedReader(new InputStreamReader(new FileInputStream(f), UTF8));
            String line;
            while ((line = br.readLine()) != null) if (line.length() > 0) out.add(line);
        } catch (Exception ignored) {
        } finally {
            try { if (br != null) br.close(); } catch (Exception ignored) {}
        }
        return out;
    }

    static String readAll(File f) throws Exception {
        FileInputStream in = new FileInputStream(f);
        try {
            byte[] buf = new byte[(int) f.length()];
            int off = 0, n;
            while (off < buf.length && (n = in.read(buf, off, buf.length - off)) > 0) off += n;
            return new String(buf, 0, off, UTF8);
        } finally {
            in.close();
        }
    }

    static void writeAll(File f, String s) throws Exception {
        Writer w = new OutputStreamWriter(new FileOutputStream(f), UTF8);
        try {
            w.write(s);
        } finally {
            w.close();
        }
    }
}
