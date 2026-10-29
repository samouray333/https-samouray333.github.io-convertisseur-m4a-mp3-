package com.echomatras.lisys;

import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.util.Xml;

import com.tom_roush.pdfbox.android.PDFBoxResourceLoader;
import com.tom_roush.pdfbox.io.MemoryUsageSetting;
import com.tom_roush.pdfbox.pdmodel.PDDocument;
import com.tom_roush.pdfbox.pdmodel.PDDocumentInformation;
import com.tom_roush.pdfbox.pdmodel.encryption.InvalidPasswordException;
import com.tom_roush.pdfbox.text.PDFTextStripper;

import org.jsoup.Jsoup;
import org.xmlpull.v1.XmlPullParser;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.Charset;
import java.nio.charset.CharsetDecoder;
import java.nio.charset.CodingErrorAction;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipFile;

/** Extraction du texte lisible des documents : PDF, Word, OpenOffice, EPUB, HTML, RTF, texte. */
public final class Extractor {
    private Extractor() {}

    public static final long MAX_FILE = 300L * 1024 * 1024;

    public static final class Result {
        public String title;
        public String kind;
        public List<String> paragraphs = new ArrayList<String>();
    }

    /** Erreur affichée telle quelle à l'utilisateur. */
    public static final class UserError extends Exception {
        public UserError(String msg) { super(msg); }
    }

    public interface Progress {
        void onProgress(String message);
    }

    // ------------------------------------------------------------------ entrée principale

    public static Result fromUri(Context c, Uri uri, Progress progress) throws Exception {
        String name = displayName(c, uri);
        String mime = c.getContentResolver().getType(uri);
        String ext = extension(name);
        if (ext.length() == 0 && mime != null) ext = extensionFromMime(mime);

        if (progress != null) progress.onProgress("Copie du fichier…");
        File tmp = new File(c.getCacheDir(), "import." + (ext.length() > 0 ? ext : "bin"));
        InputStream in = c.getContentResolver().openInputStream(uri);
        if (in == null) throw new UserError("Impossible d'ouvrir ce fichier.");
        try {
            copy(in, tmp, MAX_FILE);
        } finally {
            in.close();
        }
        try {
            Result r = fromFile(c, tmp, ext, progress);
            if (r.title == null || r.title.trim().length() == 0) r.title = stripExtension(name);
            return finish(r);
        } finally {
            tmp.delete();
        }
    }

    public static Result fromFile(Context c, File f, String ext, Progress progress) throws Exception {
        ext = ext.toLowerCase(Locale.ROOT);
        if (ext.equals("pdf")) return pdf(c, f, progress);
        if (ext.equals("docx") || ext.equals("docm") || ext.equals("dotx")) return docx(f);
        if (ext.equals("odt") || ext.equals("ott")) return odt(f);
        if (ext.equals("epub")) return epub(f, progress);
        if (ext.equals("html") || ext.equals("htm") || ext.equals("xhtml") || ext.equals("mht")) {
            Result r = WebExtractor.fromDocument(Jsoup.parse(f, null));
            r.kind = "HTML";
            return r;
        }
        if (ext.equals("rtf")) return rtf(f);
        if (ext.equals("doc")) {
            throw new UserError("L'ancien format Word .doc n'est pas pris en charge. "
                    + "Enregistre le document en .docx ou en PDF, puis rouvre-le.");
        }
        // Par défaut : on tente du texte brut, en refusant les vrais fichiers binaires.
        byte[] data = readBytes(f, 50L * 1024 * 1024);
        if (looksBinary(data)) {
            // Un PDF ou un zip mal nommé ?
            if (data.length > 4 && data[0] == '%' && data[1] == 'P' && data[2] == 'D' && data[3] == 'F') {
                return pdf(c, f, progress);
            }
            if (data.length > 4 && data[0] == 'P' && data[1] == 'K') {
                try { return docx(f); } catch (Exception ignored) {}
                try { return epub(f, progress); } catch (Exception ignored) {}
                try { return odt(f); } catch (Exception ignored) {}
            }
            throw new UserError("Ce type de fichier n'est pas pris en charge.");
        }
        Result r = plainText(decode(data), ext.equals("md"));
        r.kind = ext.equals("md") ? "MARKDOWN" : "TEXTE";
        return r;
    }

    /** Texte collé ou reçu d'une autre appli. */
    public static Result fromText(String title, String text) {
        Result r = plainText(text, false);
        r.kind = "TEXTE";
        r.title = title;
        return finish(r);
    }

    // ------------------------------------------------------------------ PDF

    private static Result pdf(Context c, File f, Progress progress) throws Exception {
        PDFBoxResourceLoader.init(c.getApplicationContext());
        PDDocument doc;
        try {
            doc = PDDocument.load(f, MemoryUsageSetting.setupMixed(24L * 1024 * 1024));
        } catch (InvalidPasswordException e) {
            throw new UserError("Ce PDF est protégé par un mot de passe.");
        }
        Result r = new Result();
        r.kind = "PDF";
        try {
            PDDocumentInformation info = doc.getDocumentInformation();
            if (info != null && info.getTitle() != null && info.getTitle().trim().length() > 2) {
                r.title = info.getTitle().trim();
            }
            PDFTextStripper st = new PDFTextStripper();
            st.setLineSeparator("\n");
            st.setParagraphEnd("\n\n");
            st.setPageEnd("\n\n");
            st.setAddMoreFormatting(true);
            int pages = doc.getNumberOfPages();
            List<List<String>> pageBlocks = new ArrayList<List<String>>();
            for (int p = 1; p <= pages; p++) {
                if (progress != null && (p == 1 || p % 5 == 0)) {
                    progress.onProgress("Lecture du PDF : page " + p + " / " + pages);
                }
                st.setStartPage(p);
                st.setEndPage(p);
                pageBlocks.add(pdfBlocks(st.getText(doc)));
            }
            removeRepeatedHeaders(pageBlocks);
            List<String> blocks = new ArrayList<String>();
            for (List<String> pb : pageBlocks) {
                // Un paragraphe coupé par un changement de page : on recolle les deux morceaux.
                if (!blocks.isEmpty() && !pb.isEmpty()) {
                    String last = blocks.get(blocks.size() - 1);
                    String first = pb.get(0);
                    if (!endsSentence(last) && Character.isLowerCase(first.charAt(0))) {
                        blocks.set(blocks.size() - 1, joinLines(last, first));
                        pb = pb.subList(1, pb.size());
                    }
                }
                blocks.addAll(pb);
            }
            for (String b : blocks) addPara(r.paragraphs, b);
        } finally {
            doc.close();
        }
        if (countChars(r.paragraphs) < 20) {
            throw new UserError("Ce PDF ne contient pas de texte lisible (c'est probablement un document "
                    + "scanné, donc une image).");
        }
        return r;
    }

    private static boolean endsSentence(String s) {
        if (s.length() == 0) return true;
        char ch = s.charAt(s.length() - 1);
        return ch == '.' || ch == '!' || ch == '?' || ch == ':' || ch == '»' || ch == '"' || ch == ';' || ch == '…';
    }

    private static boolean isPageNumber(String p) {
        return p.matches("(?i)^(page\\s*)?[-–]?\\s*\\d{1,4}\\s*[-–]?(\\s*(/|sur|of)\\s*\\d{1,4})?$");
    }

    /** "prob-" + "lème" -> "problème" ; sinon on recolle avec un espace. */
    private static String joinLines(String a, String b) {
        int n = a.length();
        if (n > 1 && a.charAt(n - 1) == '-' && Character.isLetter(a.charAt(n - 2)) && b.length() > 0
                && Character.isLowerCase(b.charAt(0))) {
            return a.substring(0, n - 1) + b;
        }
        return a + " " + b;
    }

    /** Transforme le texte d'une page en paragraphes (lignes recollées, titres séparés). */
    private static List<String> pdfBlocks(String text) {
        List<String> out = new ArrayList<String>();
        for (String b : text.split("\\n\\s*\\n")) {
            List<String> lines = new ArrayList<String>();
            int maxLen = 0;
            for (String line : b.split("\\n")) {
                String l = line.trim();
                if (l.length() == 0) continue;
                lines.add(l);
                maxLen = Math.max(maxLen, l.length());
            }
            String cur = null;
            String prev = null;
            for (String l : lines) {
                if (cur == null) { cur = l; prev = l; continue; }
                boolean prevShort = prev.length() < maxLen * 0.7;
                boolean startsUpper = Character.isUpperCase(l.charAt(0)) || Character.isDigit(l.charAt(0));
                boolean bullet = l.matches("^[\\u2022\\u25AA\\u25CF\\u2013\\u2014\\uF0B7*-]\\s.*");
                // Fin de paragraphe : ligne courte terminée par un point, ou titre court sans ponctuation.
                boolean newPara = bullet || (prevShort && startsUpper && maxLen > 30);
                if (newPara) {
                    if (!isPageNumber(cur)) out.add(cur);
                    cur = l;
                } else {
                    cur = joinLines(cur, l);
                }
                prev = l;
            }
            if (cur != null && !isPageNumber(cur)) out.add(cur);
        }
        return out;
    }

    /** Supprime les en-têtes / pieds de page répétés sur la plupart des pages. */
    private static void removeRepeatedHeaders(List<List<String>> pages) {
        if (pages.size() < 3) return;
        Map<String, Integer> count = new HashMap<String, Integer>();
        for (List<String> pb : pages) {
            Set<String> seen = new HashSet<String>();
            int n = pb.size();
            for (int i = 0; i < n; i++) {
                if (i > 1 && i < n - 2) continue; // seulement les 2 premiers et 2 derniers blocs
                String k = headerKey(pb.get(i));
                if (k.length() > 0 && k.length() < 120 && seen.add(k)) {
                    Integer c = count.get(k);
                    count.put(k, c == null ? 1 : c + 1);
                }
            }
        }
        int limit = Math.max(3, pages.size() / 2);
        for (int p = 0; p < pages.size(); p++) {
            List<String> pb = new ArrayList<String>(pages.get(p));
            int n = pb.size();
            for (int i = n - 1; i >= 0; i--) {
                if (i > 1 && i < n - 2) continue;
                Integer c = count.get(headerKey(pb.get(i)));
                if (c != null && c >= limit) pb.remove(i);
            }
            pages.set(p, pb);
        }
    }

    private static String headerKey(String s) {
        return s.replaceAll("\\d+", "#").trim().toLowerCase(Locale.ROOT);
    }

    // ------------------------------------------------------------------ Word (.docx)

    private static Result docx(File f) throws Exception {
        ZipFile zip = new ZipFile(f);
        Result r = new Result();
        r.kind = "WORD";
        try {
            ZipEntry e = zip.getEntry("word/document.xml");
            if (e == null) throw new UserError("Document Word invalide.");
            r.title = coreTitle(zip, "docProps/core.xml");
            XmlPullParser xp = Xml.newPullParser();
            xp.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false);
            InputStream in = zip.getInputStream(e);
            try {
                xp.setInput(in, "UTF-8");
                StringBuilder para = new StringBuilder();
                boolean inText = false;
                int ev;
                while ((ev = xp.next()) != XmlPullParser.END_DOCUMENT) {
                    String n = xp.getName();
                    if (ev == XmlPullParser.START_TAG) {
                        if ("w:t".equals(n)) inText = true;
                        else if ("w:tab".equals(n) || "w:br".equals(n) || "w:cr".equals(n)) para.append(' ');
                        else if ("w:noBreakHyphen".equals(n)) para.append('-');
                    } else if (ev == XmlPullParser.END_TAG) {
                        if ("w:t".equals(n)) inText = false;
                        else if ("w:p".equals(n)) {
                            addPara(r.paragraphs, para.toString());
                            para.setLength(0);
                        }
                    } else if (ev == XmlPullParser.TEXT && inText) {
                        para.append(xp.getText());
                    }
                }
                addPara(r.paragraphs, para.toString());
            } finally {
                in.close();
            }
        } finally {
            zip.close();
        }
        return r;
    }

    // ------------------------------------------------------------------ OpenOffice / LibreOffice (.odt)

    private static Result odt(File f) throws Exception {
        ZipFile zip = new ZipFile(f);
        Result r = new Result();
        r.kind = "ODT";
        try {
            ZipEntry e = zip.getEntry("content.xml");
            if (e == null) throw new UserError("Document OpenOffice invalide.");
            r.title = coreTitle(zip, "meta.xml");
            XmlPullParser xp = Xml.newPullParser();
            xp.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false);
            InputStream in = zip.getInputStream(e);
            try {
                xp.setInput(in, "UTF-8");
                StringBuilder para = new StringBuilder();
                int depth = 0; // profondeur dans text:p / text:h
                boolean inNote = false;
                int ev;
                while ((ev = xp.next()) != XmlPullParser.END_DOCUMENT) {
                    String n = xp.getName();
                    if (ev == XmlPullParser.START_TAG) {
                        if ("text:p".equals(n) || "text:h".equals(n)) {
                            if (depth > 0) { addPara(r.paragraphs, para.toString()); para.setLength(0); }
                            depth++;
                        } else if ("text:note".equals(n)) inNote = true;
                        else if ("text:s".equals(n) || "text:tab".equals(n) || "text:line-break".equals(n)) para.append(' ');
                    } else if (ev == XmlPullParser.END_TAG) {
                        if ("text:p".equals(n) || "text:h".equals(n)) {
                            depth--;
                            addPara(r.paragraphs, para.toString());
                            para.setLength(0);
                        } else if ("text:note".equals(n)) inNote = false;
                    } else if (ev == XmlPullParser.TEXT && depth > 0 && !inNote) {
                        para.append(xp.getText());
                    }
                }
            } finally {
                in.close();
            }
        } finally {
            zip.close();
        }
        return r;
    }

    private static String coreTitle(ZipFile zip, String entry) {
        try {
            ZipEntry e = zip.getEntry(entry);
            if (e == null) return null;
            XmlPullParser xp = Xml.newPullParser();
            InputStream in = zip.getInputStream(e);
            try {
                xp.setInput(in, "UTF-8");
                int ev;
                boolean inTitle = false;
                while ((ev = xp.next()) != XmlPullParser.END_DOCUMENT) {
                    if (ev == XmlPullParser.START_TAG) inTitle = "dc:title".equals(xp.getName());
                    else if (ev == XmlPullParser.END_TAG) inTitle = false;
                    else if (ev == XmlPullParser.TEXT && inTitle) {
                        String t = xp.getText().trim();
                        if (t.length() > 0) return t;
                    }
                }
            } finally {
                in.close();
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    // ------------------------------------------------------------------ EPUB

    private static Result epub(File f, Progress progress) throws Exception {
        ZipFile zip = new ZipFile(f);
        Result r = new Result();
        r.kind = "EPUB";
        try {
            ZipEntry ce = zip.getEntry("META-INF/container.xml");
            if (ce == null) throw new UserError("Livre EPUB invalide.");
            org.jsoup.nodes.Document container = Jsoup.parse(readEntry(zip, ce), "", org.jsoup.parser.Parser.xmlParser());
            org.jsoup.nodes.Element rootfile = container.selectFirst("rootfile");
            if (rootfile == null) throw new UserError("Livre EPUB invalide.");
            String opfPath = rootfile.attr("full-path");
            String base = opfPath.contains("/") ? opfPath.substring(0, opfPath.lastIndexOf('/') + 1) : "";
            ZipEntry oe = zip.getEntry(opfPath);
            if (oe == null) throw new UserError("Livre EPUB invalide.");
            org.jsoup.nodes.Document opf = Jsoup.parse(readEntry(zip, oe), "", org.jsoup.parser.Parser.xmlParser());
            for (org.jsoup.nodes.Element t : opf.getAllElements()) {
                if (t.tagName().equalsIgnoreCase("dc:title") && t.text().trim().length() > 0) {
                    r.title = t.text().trim();
                    break;
                }
            }
            Map<String, String> hrefs = new HashMap<String, String>();
            for (org.jsoup.nodes.Element it : opf.select("manifest > item")) hrefs.put(it.attr("id"), it.attr("href"));
            org.jsoup.select.Elements spine = opf.select("spine > itemref");
            int i = 0;
            for (org.jsoup.nodes.Element ref : spine) {
                i++;
                if (progress != null) progress.onProgress("Lecture du livre : chapitre " + i + " / " + spine.size());
                String href = hrefs.get(ref.attr("idref"));
                if (href == null) continue;
                String path = normalizePath(base + Uri.decode(href));
                ZipEntry xe = zip.getEntry(path);
                if (xe == null) continue;
                org.jsoup.nodes.Document x = Jsoup.parse(readEntry(zip, xe));
                WebExtractor.collectBlocks(x.body(), r.paragraphs);
            }
        } finally {
            zip.close();
        }
        if (r.paragraphs.isEmpty()) throw new UserError("Ce livre ne contient pas de texte lisible.");
        return r;
    }

    private static String normalizePath(String p) {
        List<String> parts = new ArrayList<String>();
        for (String s : p.split("/")) {
            if (s.equals("..")) { if (!parts.isEmpty()) parts.remove(parts.size() - 1); }
            else if (s.length() > 0 && !s.equals(".")) parts.add(s);
        }
        StringBuilder sb = new StringBuilder();
        for (String s : parts) { if (sb.length() > 0) sb.append('/'); sb.append(s); }
        return sb.toString();
    }

    private static String readEntry(ZipFile zip, ZipEntry e) throws Exception {
        InputStream in = zip.getInputStream(e);
        try {
            return decode(readStream(in, 50L * 1024 * 1024));
        } finally {
            in.close();
        }
    }

    // ------------------------------------------------------------------ RTF

    private static Result rtf(File f) throws Exception {
        byte[] data = readBytes(f, 50L * 1024 * 1024);
        String s = new String(data, Charset.forName("ISO-8859-1"));
        StringBuilder out = new StringBuilder();
        Charset cp = Charset.forName("windows-1252");
        int depth = 0;
        int skipDepth = -1; // groupe ignoré (police, styles, images…)
        int ucSkip = 1;
        int pendingSkip = 0;
        int i = 0, n = s.length();
        while (i < n) {
            char ch = s.charAt(i);
            if (ch == '{') { depth++; i++; continue; }
            if (ch == '}') { if (depth == skipDepth) skipDepth = -1; depth--; i++; continue; }
            boolean skipping = skipDepth >= 0 && depth >= skipDepth;
            if (ch == '\\') {
                if (i + 1 >= n) break;
                char nx = s.charAt(i + 1);
                if (nx == '\\' || nx == '{' || nx == '}') {
                    if (!skipping) out.append(nx);
                    i += 2;
                    continue;
                }
                if (nx == '\'') {
                    if (i + 3 < n && !skipping) {
                        if (pendingSkip > 0) pendingSkip--;
                        else {
                            try {
                                int v = Integer.parseInt(s.substring(i + 2, i + 4), 16);
                                out.append(new String(new byte[]{(byte) v}, cp));
                            } catch (Exception ignored) {}
                        }
                    }
                    i += 4;
                    continue;
                }
                if (nx == '*') { if (skipDepth < 0) skipDepth = depth; i += 2; continue; }
                if (nx == '~') { if (!skipping) out.append(' '); i += 2; continue; }
                if (nx == '-' || nx == '_') { i += 2; continue; }
                int j = i + 1;
                while (j < n && Character.isLetter(s.charAt(j))) j++;
                String word = s.substring(i + 1, j);
                int k = j;
                if (k < n && (s.charAt(k) == '-' || Character.isDigit(s.charAt(k)))) {
                    k++;
                    while (k < n && Character.isDigit(s.charAt(k))) k++;
                }
                String param = s.substring(j, k);
                if (k < n && s.charAt(k) == ' ') k++;
                i = k;
                if (word.length() == 0) { i = j + 1; continue; }
                if (word.equals("fonttbl") || word.equals("colortbl") || word.equals("stylesheet")
                        || word.equals("info") || word.equals("pict") || word.equals("header")
                        || word.equals("footer") || word.equals("object") || word.equals("themedata")
                        || word.equals("datastore") || word.equals("latentstyles")) {
                    if (skipDepth < 0) skipDepth = depth;
                    continue;
                }
                if (skipping) continue;
                if (word.equals("par") || word.equals("line") || word.equals("sect") || word.equals("page")) out.append('\n');
                else if (word.equals("tab") || word.equals("cell")) out.append(' ');
                else if (word.equals("row")) out.append('\n');
                else if (word.equals("uc")) { try { ucSkip = Integer.parseInt(param); } catch (Exception ignored) {} }
                else if (word.equals("u")) {
                    try {
                        int v = Integer.parseInt(param);
                        if (v < 0) v += 65536;
                        out.append((char) v);
                        pendingSkip = ucSkip;
                    } catch (Exception ignored) {}
                } else if (word.equals("emdash")) out.append('—');
                else if (word.equals("endash")) out.append('–');
                else if (word.equals("lquote") || word.equals("rquote")) out.append('\'');
                else if (word.equals("ldblquote") || word.equals("rdblquote")) out.append('"');
                continue;
            }
            if (ch == '\r' || ch == '\n') { i++; continue; }
            if (!skipping) {
                if (pendingSkip > 0) pendingSkip--;
                else out.append(ch);
            }
            i++;
        }
        Result r = new Result();
        r.kind = "RTF";
        for (String line : out.toString().split("\n")) addPara(r.paragraphs, line);
        return r;
    }

    // ------------------------------------------------------------------ texte brut

    static Result plainText(String text, boolean markdown) {
        Result r = new Result();
        text = text.replace("\r\n", "\n").replace('\r', '\n');
        if (text.length() > 0 && text.charAt(0) == '﻿') text = text.substring(1);
        String[] lines = text.split("\n");
        int blank = 0, nonBlank = 0;
        for (String l : lines) { if (l.trim().length() == 0) blank++; else nonBlank++; }
        // Texte "à l'ancienne" : lignes coupées à ~70 caractères, paragraphes séparés par une ligne vide.
        boolean wrapped = blank > 0 && nonBlank > blank * 2;
        StringBuilder para = new StringBuilder();
        for (String raw : lines) {
            String l = raw.trim();
            if (markdown) l = cleanMarkdown(l);
            if (l.length() == 0) {
                addPara(r.paragraphs, para.toString());
                para.setLength(0);
                continue;
            }
            if (wrapped) {
                if (para.length() > 0) para.append(' ');
                para.append(l);
            } else {
                addPara(r.paragraphs, l);
            }
        }
        addPara(r.paragraphs, para.toString());
        return r;
    }

    private static String cleanMarkdown(String l) {
        l = l.replaceAll("^#{1,6}\\s+", "");
        l = l.replaceAll("^[-*+]\\s+", "");
        l = l.replaceAll("^>\\s?", "");
        l = l.replaceAll("!\\[([^\\]]*)\\]\\([^)]*\\)", "$1");
        l = l.replaceAll("\\[([^\\]]*)\\]\\([^)]*\\)", "$1");
        l = l.replaceAll("[*_`]{1,3}", "");
        if (l.matches("^[-=*_\\s|:]+$")) return "";
        return l.trim();
    }

    // ------------------------------------------------------------------ utilitaires

    static void addPara(List<String> out, String p) {
        if (p == null) return;
        p = p.replace('\u00A0', ' ').replace('\u200B', ' ')
                .replaceAll("[\\uE000-\\uF8FF]", " ")   // symboles des polices Symbol/Wingdings
                .replaceAll("\\s+", " ").trim();
        // Puces de liste en début de ligne : inutile de les prononcer.
        p = p.replaceFirst("^[\\u2022\\u00B7\\u25AA\\u25E6\\u25CF\\u25CB\\u25A0\\u27A4\\u25BA\\u2013\\u2014*]+\\s+", "");
        if (p.length() == 0) return;
        // Ignore les lignes faites uniquement de symboles (décors, séparateurs).
        boolean hasLetterOrDigit = false;
        for (int i = 0; i < p.length(); i++) {
            if (Character.isLetterOrDigit(p.charAt(i))) { hasLetterOrDigit = true; break; }
        }
        if (!hasLetterOrDigit) return;
        out.add(p);
    }

    /** Découpe les paragraphes géants (pour garder l'affichage fluide) et nettoie le titre. */
    static Result finish(Result r) {
        List<String> out = new ArrayList<String>();
        for (String p : r.paragraphs) {
            if (p.length() <= 1500) { out.add(p); continue; }
            List<String> sents = Sentences.split(p);
            StringBuilder sb = new StringBuilder();
            for (String s : sents) {
                if (sb.length() + s.length() > 1200 && sb.length() > 0) {
                    out.add(sb.toString().trim());
                    sb.setLength(0);
                }
                sb.append(s).append(' ');
            }
            if (sb.toString().trim().length() > 0) out.add(sb.toString().trim());
        }
        r.paragraphs = out;
        if (r.title == null || r.title.trim().length() == 0) {
            r.title = out.isEmpty() ? "Sans titre" : out.get(0);
        }
        r.title = r.title.replaceAll("\\s+", " ").trim();
        if (r.title.length() > 120) r.title = r.title.substring(0, 117) + "…";
        return r;
    }

    static int countChars(List<String> l) {
        int n = 0;
        for (String s : l) n += s.length();
        return n;
    }

    public static String displayName(Context c, Uri uri) {
        String name = null;
        if ("content".equals(uri.getScheme())) {
            Cursor cur = null;
            try {
                cur = c.getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null);
                if (cur != null && cur.moveToFirst()) name = cur.getString(0);
            } catch (Exception ignored) {
            } finally {
                if (cur != null) cur.close();
            }
        }
        if (name == null) name = uri.getLastPathSegment();
        if (name == null) name = "document";
        return name;
    }

    static String extension(String name) {
        int dot = name.lastIndexOf('.');
        if (dot < 0 || dot == name.length() - 1) return "";
        String e = name.substring(dot + 1).toLowerCase(Locale.ROOT);
        return e.length() > 5 ? "" : e;
    }

    static String stripExtension(String name) {
        int dot = name.lastIndexOf('.');
        return dot > 0 ? name.substring(0, dot) : name;
    }

    static String extensionFromMime(String mime) {
        mime = mime.toLowerCase(Locale.ROOT);
        if (mime.contains("pdf")) return "pdf";
        if (mime.contains("wordprocessingml")) return "docx";
        if (mime.contains("opendocument.text")) return "odt";
        if (mime.contains("epub")) return "epub";
        if (mime.contains("html")) return "html";
        if (mime.contains("rtf")) return "rtf";
        if (mime.contains("msword")) return "doc";
        if (mime.contains("markdown")) return "md";
        if (mime.startsWith("text/")) return "txt";
        return "";
    }

    static void copy(InputStream in, File out, long max) throws Exception {
        OutputStream os = new FileOutputStream(out);
        try {
            byte[] buf = new byte[64 * 1024];
            long total = 0;
            int n;
            while ((n = in.read(buf)) > 0) {
                total += n;
                if (total > max) throw new UserError("Fichier trop volumineux.");
                os.write(buf, 0, n);
            }
        } finally {
            os.close();
        }
    }

    static byte[] readBytes(File f, long max) throws Exception {
        if (f.length() > max) throw new UserError("Fichier trop volumineux.");
        FileInputStream in = new FileInputStream(f);
        try {
            return readStream(in, max);
        } finally {
            in.close();
        }
    }

    static byte[] readStream(InputStream in, long max) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[64 * 1024];
        long total = 0;
        int n;
        while ((n = in.read(buf)) > 0) {
            total += n;
            if (total > max) throw new UserError("Fichier trop volumineux.");
            bos.write(buf, 0, n);
        }
        return bos.toByteArray();
    }

    private static boolean looksBinary(byte[] d) {
        int n = Math.min(d.length, 8192), zeros = 0;
        for (int i = 0; i < n; i++) if (d[i] == 0) zeros++;
        // UTF-16 contient beaucoup de zéros mais commence par un BOM.
        if (n >= 2 && ((d[0] == (byte) 0xFF && d[1] == (byte) 0xFE) || (d[0] == (byte) 0xFE && d[1] == (byte) 0xFF))) return false;
        return zeros > 0;
    }

    /** Décode en UTF-8 si c'est valide, sinon en Windows-1252 (fichiers Windows anciens). */
    static String decode(byte[] d) {
        if (d.length >= 2 && d[0] == (byte) 0xFF && d[1] == (byte) 0xFE) return new String(d, 2, d.length - 2, Charset.forName("UTF-16LE"));
        if (d.length >= 2 && d[0] == (byte) 0xFE && d[1] == (byte) 0xFF) return new String(d, 2, d.length - 2, Charset.forName("UTF-16BE"));
        CharsetDecoder dec = Charset.forName("UTF-8").newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT);
        try {
            CharBuffer cb = dec.decode(ByteBuffer.wrap(d));
            return cb.toString();
        } catch (CharacterCodingException e) {
            return new String(d, Charset.forName("windows-1252"));
        }
    }
}
