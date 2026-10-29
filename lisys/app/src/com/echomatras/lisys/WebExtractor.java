package com.echomatras.lisys;

import android.content.Context;

import org.jsoup.Connection;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.nodes.Node;
import org.jsoup.nodes.TextNode;
import org.jsoup.select.Elements;

import java.io.File;
import java.io.FileOutputStream;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Récupère une page web et garde seulement le texte de l'article
 * (sans menus, pubs, bandeaux cookies, pieds de page…).
 */
public final class WebExtractor {
    private WebExtractor() {}

    static final String USER_AGENT = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
            + "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36";

    private static final String JUNK = "script,style,noscript,iframe,svg,canvas,form,nav,footer,aside,"
            + "button,select,input,textarea,template,dialog,menu,"
            + "[aria-hidden=true],[hidden],[role=navigation],[role=banner],[role=contentinfo],"
            + "[role=complementary],[role=dialog],[role=alert]";

    private static final String[] JUNK_WORDS = {
            "cookie", "consent", "gdpr", "rgpd", "newsletter", "share", "partage", "social", "comment",
            "related", "sidebar", "advert", "publicite", "promo", "breadcrumb", "subscribe", "abonnement",
            "popup", "modal", "banner", "footer", "menu", "nav", "outbrain", "taboola", "sponsor",
            "paywall", "toolbar", "skip-link", "visually-hidden", "sr-only"};

    private static final Set<String> BLOCKS = new HashSet<String>();
    static {
        for (String t : new String[]{"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre",
                "dd", "dt", "figcaption", "td", "th", "caption", "summary"}) BLOCKS.add(t);
    }

    public static Extractor.Result fromUrl(Context c, String url, Extractor.Progress progress) throws Exception {
        url = normalizeUrl(url);
        if (progress != null) progress.onProgress("Téléchargement de la page…");
        Connection.Response resp;
        try {
            resp = Jsoup.connect(url)
                    .userAgent(USER_AGENT)
                    .header("Accept-Language", "fr-FR,fr;q=0.9,en;q=0.6")
                    .timeout(25000)
                    .followRedirects(true)
                    .ignoreContentType(true)
                    .ignoreHttpErrors(true)
                    .maxBodySize(40 * 1024 * 1024)
                    .execute();
        } catch (java.net.UnknownHostException e) {
            throw new Extractor.UserError("Site introuvable. Vérifie l'adresse et la connexion internet.");
        } catch (java.net.SocketTimeoutException e) {
            throw new Extractor.UserError("Le site met trop de temps à répondre.");
        }
        if (resp.statusCode() >= 400) {
            throw new Extractor.UserError("Le site a refusé la page (erreur " + resp.statusCode()
                    + "). Essaie avec le navigateur intégré.");
        }
        String type = resp.contentType() == null ? "" : resp.contentType().toLowerCase(Locale.ROOT);
        String path = resp.url().getPath().toLowerCase(Locale.ROOT);
        if (type.contains("pdf") || path.endsWith(".pdf") || type.contains("epub") || type.contains("wordprocessingml")) {
            String ext = type.contains("pdf") || path.endsWith(".pdf") ? "pdf" : type.contains("epub") ? "epub" : "docx";
            File tmp = new File(c.getCacheDir(), "web." + ext);
            FileOutputStream os = new FileOutputStream(tmp);
            try {
                os.write(resp.bodyAsBytes());
            } finally {
                os.close();
            }
            try {
                Extractor.Result r = Extractor.fromFile(c, tmp, ext, progress);
                if (r.title == null) r.title = Extractor.stripExtension(Extractor.displayName(c, android.net.Uri.parse(url)));
                return Extractor.finish(r);
            } finally {
                tmp.delete();
            }
        }
        if (type.startsWith("text/plain")) {
            Extractor.Result r = Extractor.plainText(resp.body(), false);
            r.kind = "WEB";
            return Extractor.finish(r);
        }
        if (progress != null) progress.onProgress("Extraction du texte…");
        Document doc = resp.parse();
        Extractor.Result r = fromDocument(doc);
        r.kind = "WEB";
        if (r.paragraphs.isEmpty()) {
            throw new Extractor.UserError("Aucun texte trouvé sur cette page. Si le site a besoin de JavaScript "
                    + "ou d'une connexion, ouvre-la avec le navigateur intégré.");
        }
        return Extractor.finish(r);
    }

    /** Utilisé par le navigateur intégré : la page a déjà été chargée (JavaScript, connexion…). */
    public static Extractor.Result fromHtml(String html, String baseUrl) {
        Extractor.Result r = fromDocument(Jsoup.parse(html, baseUrl));
        r.kind = "WEB";
        return Extractor.finish(r);
    }

    public static String normalizeUrl(String url) {
        url = url.trim();
        if (!url.matches("(?i)^https?://.*")) url = "https://" + url;
        return url;
    }

    public static Extractor.Result fromDocument(Document doc) {
        Extractor.Result r = new Extractor.Result();
        r.title = title(doc);
        Element body = doc.body();
        if (body == null) return r;
        clean(body);
        Element root = pickRoot(body);
        collectBlocks(root, r.paragraphs);
        // Si l'article choisi est trop pauvre, on se rabat sur toute la page.
        if (Extractor.countChars(r.paragraphs) < 300 && root != body) {
            r.paragraphs.clear();
            collectBlocks(body, r.paragraphs);
        }
        // Le titre est lu en premier, sauf s'il figure déjà en tête d'article.
        if (r.title != null && r.title.length() > 0) {
            boolean present = false;
            for (int i = 0; i < Math.min(3, r.paragraphs.size()); i++) {
                if (r.paragraphs.get(i).equalsIgnoreCase(r.title)) present = true;
            }
            if (!present) r.paragraphs.add(0, r.title);
        }
        return r;
    }

    private static String title(Document doc) {
        Element og = doc.selectFirst("meta[property=og:title]");
        if (og != null && og.attr("content").trim().length() > 0) return og.attr("content").trim();
        Element h1 = doc.selectFirst("article h1, main h1, h1");
        if (h1 != null && h1.text().trim().length() > 0) return h1.text().trim();
        String t = doc.title();
        return t == null ? null : t.trim();
    }

    private static void clean(Element body) {
        body.select(JUNK).remove();
        for (Element e : body.getAllElements()) {
            if (e == body || e.parent() == null) continue;
            String tag = e.tagName();
            if (tag.equals("article") || tag.equals("main") || tag.equals("p")) continue;
            String idc = (e.id() + " " + e.className()).toLowerCase(Locale.ROOT);
            if (idc.trim().length() == 0) continue;
            for (String w : JUNK_WORDS) {
                if (idc.contains(w)) {
                    // On évite de supprimer un gros bloc d'article qui aurait juste "comment" dans sa classe.
                    if (e.text().length() < 1500 || w.equals("cookie") || w.equals("consent")) e.remove();
                    break;
                }
            }
        }
    }

    /** Choisit le bloc qui contient le plus de vrais paragraphes de texte. */
    private static Element pickRoot(Element body) {
        Elements articles = body.select("article, main, [role=main], [itemprop=articleBody]");
        Element best = null;
        int bestLen = 0;
        for (Element a : articles) {
            int len = paragraphText(a);
            if (len > bestLen) { best = a; bestLen = len; }
        }
        if (best != null && bestLen > 500) return best;

        Map<Element, Integer> scores = new HashMap<Element, Integer>();
        for (Element p : body.select("p")) {
            int len = p.text().length();
            if (len < 40) continue;
            int score = len + 100 * countCommas(p.text());
            Element parent = p.parent();
            if (parent == null) continue;
            add(scores, parent, score);
            if (parent.parent() != null) add(scores, parent.parent(), score / 2);
        }
        Element top = null;
        int topScore = 0;
        for (Map.Entry<Element, Integer> e : scores.entrySet()) {
            if (e.getValue() > topScore) { top = e.getKey(); topScore = e.getValue(); }
        }
        return top != null ? top : body;
    }

    private static int countCommas(String s) {
        int n = 0;
        for (int i = 0; i < s.length(); i++) if (s.charAt(i) == ',') n++;
        return Math.min(n, 10);
    }

    private static void add(Map<Element, Integer> m, Element e, int v) {
        Integer old = m.get(e);
        m.put(e, old == null ? v : old + v);
    }

    private static int paragraphText(Element e) {
        int n = 0;
        for (Element p : e.select("p")) n += p.text().length();
        return n;
    }

    /**
     * Parcourt le bloc dans l'ordre et sort un paragraphe par bloc de texte
     * (titres, paragraphes, listes…). Le texte "libre" dans les div est aussi récupéré.
     */
    public static void collectBlocks(Element root, List<String> out) {
        if (root == null) return;
        StringBuilder loose = new StringBuilder();
        walk(root, out, loose);
        Extractor.addPara(out, loose.toString());
    }

    private static void walk(Node node, List<String> out, StringBuilder loose) {
        for (Node child : node.childNodes()) {
            if (child instanceof TextNode) {
                String t = ((TextNode) child).text();
                loose.append(t.trim().length() > 0 ? t : " ");
                continue;
            }
            if (!(child instanceof Element)) continue;
            Element e = (Element) child;
            String tag = e.tagName().toLowerCase(Locale.ROOT);
            if (tag.equals("br")) { loose.append(' '); continue; }
            if (tag.equals("script") || tag.equals("style") || tag.equals("noscript")) continue;
            if (BLOCKS.contains(tag) && !hasBlockChild(e)) {
                Extractor.addPara(out, loose.toString());
                loose.setLength(0);
                String t = e.text();
                if (tag.equals("li") && t.length() < 3) continue;
                Extractor.addPara(out, t);
                continue;
            }
            boolean isBlock = e.isBlock();
            if (isBlock) { Extractor.addPara(out, loose.toString()); loose.setLength(0); }
            walk(e, out, loose);
            if (isBlock) { Extractor.addPara(out, loose.toString()); loose.setLength(0); }
        }
    }

    private static boolean hasBlockChild(Element e) {
        for (Element d : e.getAllElements()) {
            if (d == e) continue;
            String t = d.tagName().toLowerCase(Locale.ROOT);
            if (BLOCKS.contains(t) || t.equals("div") || t.equals("section") || t.equals("ul") || t.equals("ol")
                    || t.equals("table")) return true;
        }
        return false;
    }
}
