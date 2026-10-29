using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using HtmlAgilityPack;

namespace Lisys
{
    /// <summary>
    /// Récupère une page web et garde seulement le texte de l'article
    /// (sans menus, pubs, bandeaux cookies, pieds de page…).
    /// </summary>
    public static class WebExtractor
    {
        const string UserAgent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

        static readonly HashSet<string> JunkTags = new HashSet<string>
        {
            "script", "style", "noscript", "iframe", "svg", "canvas", "form", "nav", "footer", "aside", "button",
            "select", "input", "textarea", "template", "dialog", "menu", "head"
        };

        static readonly string[] JunkRoles = { "navigation", "banner", "contentinfo", "complementary", "dialog", "alert" };

        static readonly string[] JunkWords =
        {
            "cookie", "consent", "gdpr", "rgpd", "newsletter", "share", "partage", "social", "comment", "related",
            "sidebar", "advert", "publicite", "promo", "breadcrumb", "subscribe", "abonnement", "popup", "modal",
            "banner", "footer", "menu", "nav", "outbrain", "taboola", "sponsor", "paywall", "toolbar", "skip-link",
            "visually-hidden", "sr-only"
        };

        static readonly HashSet<string> Blocks = new HashSet<string>
        {
            "h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre", "dd", "dt", "figcaption", "td", "th",
            "caption", "summary"
        };

        static readonly HashSet<string> BlockLevel = new HashSet<string>
        {
            "div", "section", "article", "main", "header", "footer", "ul", "ol", "table", "tr", "tbody", "thead",
            "dl", "figure", "body", "html", "address", "center", "details", "fieldset", "hr", "aside", "nav", "br"
        };

        static readonly HttpClient Http = CreateClient();

        static HttpClient CreateClient()
        {
            ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12 | (SecurityProtocolType)12288; // TLS 1.3 si disponible
            var h = new HttpClientHandler { AllowAutoRedirect = true, AutomaticDecompression = DecompressionMethods.GZip | DecompressionMethods.Deflate };
            var c = new HttpClient(h) { Timeout = TimeSpan.FromSeconds(25) };
            c.DefaultRequestHeaders.UserAgent.ParseAdd(UserAgent);
            c.DefaultRequestHeaders.AcceptLanguage.ParseAdd("fr-FR,fr;q=0.9,en;q=0.6");
            return c;
        }

        public static string NormalizeUrl(string url)
        {
            url = url.Trim();
            if (!Regex.IsMatch(url, "^https?://", RegexOptions.IgnoreCase)) url = "https://" + url;
            return url;
        }

        public static ExtractResult FromUrl(string url, Action<string> progress)
        {
            url = NormalizeUrl(url);
            progress?.Invoke("Téléchargement de la page…");
            HttpResponseMessage resp;
            try
            {
                resp = Http.GetAsync(url).GetAwaiter().GetResult();
            }
            catch (HttpRequestException)
            {
                throw new UserException("Site introuvable. Vérifie l'adresse et la connexion internet.");
            }
            catch (System.Threading.Tasks.TaskCanceledException)
            {
                throw new UserException("Le site met trop de temps à répondre.");
            }
            using (resp)
            {
                if ((int)resp.StatusCode >= 400)
                    throw new UserException("Le site a refusé la page (erreur " + (int)resp.StatusCode + ").");
                string type = resp.Content.Headers.ContentType?.MediaType?.ToLowerInvariant() ?? "";
                string path = resp.RequestMessage.RequestUri.AbsolutePath.ToLowerInvariant();
                byte[] body = resp.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult();
                if (type.Contains("pdf") || path.EndsWith(".pdf") || type.Contains("epub") || type.Contains("wordprocessingml"))
                {
                    string ext = type.Contains("pdf") || path.EndsWith(".pdf") ? ".pdf" : type.Contains("epub") ? ".epub" : ".docx";
                    string tmp = Path.Combine(Path.GetTempPath(), "lisys-web" + ext);
                    File.WriteAllBytes(tmp, body);
                    try
                    {
                        var r = Extractor.FromFile(tmp, progress);
                        if (r.Title == "lisys-web") r.Title = Path.GetFileNameWithoutExtension(Uri.UnescapeDataString(path));
                        return r;
                    }
                    finally
                    {
                        try { File.Delete(tmp); } catch { }
                    }
                }
                string charset = resp.Content.Headers.ContentType?.CharSet;
                string html = DecodeBody(body, charset);
                if (type.StartsWith("text/plain"))
                {
                    var t = Extractor.PlainText(html, false);
                    t.Kind = "WEB";
                    return Extractor.Finish(t);
                }
                progress?.Invoke("Extraction du texte…");
                var res = FromHtml(html, url);
                res.Kind = "WEB";
                if (res.Paragraphs.Count == 0)
                    throw new UserException("Aucun texte trouvé sur cette page. Si le site demande une connexion, ouvre la page dans ton navigateur, sélectionne le texte et appuie sur Ctrl+Alt+L.");
                return res;
            }
        }

        static string DecodeBody(byte[] body, string charset)
        {
            if (!string.IsNullOrEmpty(charset))
            {
                try { return Encoding.GetEncoding(charset.Trim('"')).GetString(body); } catch { }
            }
            string head = Encoding.ASCII.GetString(body, 0, Math.Min(body.Length, 4096));
            var m = Regex.Match(head, "charset=[\"']?([A-Za-z0-9_-]+)", RegexOptions.IgnoreCase);
            if (m.Success)
            {
                try { return Encoding.GetEncoding(m.Groups[1].Value).GetString(body); } catch { }
            }
            return Extractor.Decode(body);
        }

        public static ExtractResult FromHtml(string html, string baseUrl)
        {
            var doc = new HtmlDocument();
            doc.LoadHtml(html);
            var r = new ExtractResult { Kind = "WEB", Title = Title(doc) };
            var body = doc.DocumentNode.SelectSingleNode("//body") ?? doc.DocumentNode;
            Clean(body);
            var root = PickRoot(body);
            CollectBlocks(root, r.Paragraphs);
            if (Extractor.CountChars(r.Paragraphs) < 300 && root != body)
            {
                r.Paragraphs.Clear();
                CollectBlocks(body, r.Paragraphs);
            }
            // Le titre est lu en premier, sauf s'il figure déjà en tête d'article.
            if (!string.IsNullOrEmpty(r.Title) && !r.Paragraphs.Take(3).Any(p => string.Equals(p, r.Title, StringComparison.OrdinalIgnoreCase)))
                r.Paragraphs.Insert(0, r.Title);
            return Extractor.Finish(r);
        }

        static string Text(HtmlNode n) => Regex.Replace(HtmlEntity.DeEntitize(n.InnerText ?? ""), @"\s+", " ").Trim();

        static string Title(HtmlDocument doc)
        {
            var og = doc.DocumentNode.SelectSingleNode("//meta[@property='og:title']");
            string v = og?.GetAttributeValue("content", "");
            if (!string.IsNullOrWhiteSpace(v)) return HtmlEntity.DeEntitize(v).Trim();
            var h1 = doc.DocumentNode.SelectSingleNode("//article//h1") ?? doc.DocumentNode.SelectSingleNode("//main//h1") ?? doc.DocumentNode.SelectSingleNode("//h1");
            if (h1 != null && Text(h1).Length > 0) return Text(h1);
            var t = doc.DocumentNode.SelectSingleNode("//title");
            return t == null ? null : Text(t);
        }

        static void Clean(HtmlNode body)
        {
            foreach (var n in body.Descendants().ToList())
            {
                if (n.NodeType == HtmlNodeType.Comment) { n.Remove(); continue; }
                if (n.NodeType != HtmlNodeType.Element || n.ParentNode == null) continue;
                string tag = n.Name.ToLowerInvariant();
                if (JunkTags.Contains(tag)) { n.Remove(); continue; }
                string role = n.GetAttributeValue("role", "").ToLowerInvariant();
                if (n.GetAttributeValue("aria-hidden", "") == "true" || n.Attributes.Contains("hidden") || JunkRoles.Contains(role))
                {
                    n.Remove();
                    continue;
                }
                if (tag == "article" || tag == "main" || tag == "p") continue;
                string idc = (n.Id + " " + n.GetAttributeValue("class", "")).ToLowerInvariant();
                if (idc.Trim().Length == 0) continue;
                foreach (var w in JunkWords)
                {
                    if (!idc.Contains(w)) continue;
                    // On évite de supprimer un gros bloc d'article qui aurait juste « comment » dans sa classe.
                    if (w == "cookie" || w == "consent" || Text(n).Length < 1500) n.Remove();
                    break;
                }
            }
        }

        static HtmlNode PickRoot(HtmlNode body)
        {
            HtmlNode best = null;
            int bestLen = 0;
            foreach (var a in body.Descendants().Where(n => n.Name == "article" || n.Name == "main"
                     || n.GetAttributeValue("role", "") == "main" || n.GetAttributeValue("itemprop", "") == "articleBody"))
            {
                int len = a.Descendants("p").Sum(p => Text(p).Length);
                if (len > bestLen) { best = a; bestLen = len; }
            }
            if (best != null && bestLen > 500) return best;

            var scores = new Dictionary<HtmlNode, int>();
            foreach (var p in body.Descendants("p"))
            {
                string t = Text(p);
                if (t.Length < 40) continue;
                int score = t.Length + 100 * Math.Min(10, t.Count(c => c == ','));
                var parent = p.ParentNode;
                if (parent == null) continue;
                scores[parent] = (scores.TryGetValue(parent, out int s1) ? s1 : 0) + score;
                if (parent.ParentNode != null) scores[parent.ParentNode] = (scores.TryGetValue(parent.ParentNode, out int s2) ? s2 : 0) + score / 2;
            }
            var top = scores.OrderByDescending(kv => kv.Value).FirstOrDefault();
            return top.Key ?? body;
        }

        /// <summary>Un paragraphe par bloc de texte (titres, paragraphes, listes…), dans l'ordre.</summary>
        public static void CollectBlocks(HtmlNode root, List<string> output)
        {
            if (root == null) return;
            var loose = new StringBuilder();
            Walk(root, output, loose);
            Extractor.AddPara(output, loose.ToString());
        }

        static void Walk(HtmlNode node, List<string> output, StringBuilder loose)
        {
            foreach (var child in node.ChildNodes)
            {
                if (child.NodeType == HtmlNodeType.Text)
                {
                    string t = HtmlEntity.DeEntitize(((HtmlTextNode)child).Text);
                    loose.Append(t.Trim().Length > 0 ? t : " ");
                    continue;
                }
                if (child.NodeType != HtmlNodeType.Element) continue;
                string tag = child.Name.ToLowerInvariant();
                if (tag == "br") { loose.Append(' '); continue; }
                if (tag == "script" || tag == "style" || tag == "noscript") continue;
                if (Blocks.Contains(tag) && !HasBlockChild(child))
                {
                    Extractor.AddPara(output, loose.ToString());
                    loose.Clear();
                    string t = Text(child);
                    if (tag == "li" && t.Length < 3) continue;
                    Extractor.AddPara(output, t);
                    continue;
                }
                bool isBlock = BlockLevel.Contains(tag) || Blocks.Contains(tag);
                if (isBlock) { Extractor.AddPara(output, loose.ToString()); loose.Clear(); }
                Walk(child, output, loose);
                if (isBlock) { Extractor.AddPara(output, loose.ToString()); loose.Clear(); }
            }
        }

        static bool HasBlockChild(HtmlNode e)
        {
            foreach (var d in e.Descendants())
            {
                if (d.NodeType != HtmlNodeType.Element) continue;
                string t = d.Name.ToLowerInvariant();
                if (Blocks.Contains(t) || t == "div" || t == "section" || t == "ul" || t == "ol" || t == "table") return true;
            }
            return false;
        }
    }
}
