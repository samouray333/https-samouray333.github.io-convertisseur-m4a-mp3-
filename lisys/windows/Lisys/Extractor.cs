using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;
using System.Xml.Linq;
using UglyToad.PdfPig;
using UglyToad.PdfPig.Content;
using UglyToad.PdfPig.DocumentLayoutAnalysis.PageSegmenter;
using UglyToad.PdfPig.DocumentLayoutAnalysis.ReadingOrderDetector;
using UglyToad.PdfPig.DocumentLayoutAnalysis.WordExtractor;

namespace Lisys
{
    public sealed class ExtractResult
    {
        public string Title;
        public string Kind;
        public List<string> Paragraphs = new List<string>();
    }

    /// <summary>Erreur affichée telle quelle à l'utilisateur.</summary>
    public class UserException : Exception
    {
        public UserException(string message) : base(message) { }
    }

    /// <summary>PDF sans texte (document scanné) : à lire avec la reconnaissance de texte.</summary>
    public sealed class NeedsOcrException : UserException
    {
        public NeedsOcrException(string message) : base(message) { }
    }

    /// <summary>Extraction du texte lisible : PDF, Word, OpenOffice, EPUB, HTML, RTF, texte.</summary>
    public static class Extractor
    {
        public const long MaxFile = 300L * 1024 * 1024;

        public static readonly string[] ImageExtensions = { "jpg", "jpeg", "png", "bmp", "gif", "tif", "tiff", "webp", "heic" };
        public static readonly string[] DocumentExtensions = { "pdf", "docx", "docm", "dotx", "odt", "ott", "epub", "html", "htm", "xhtml", "rtf", "txt", "md", "csv", "srt", "log" };

        public static bool IsImage(string path) => ImageExtensions.Contains(Ext(path));

        public static string Ext(string path) => Path.GetExtension(path ?? "").TrimStart('.').ToLowerInvariant();

        public static ExtractResult FromFile(string path, Action<string> progress)
        {
            var fi = new FileInfo(path);
            if (!fi.Exists) throw new UserException("Fichier introuvable.");
            if (fi.Length > MaxFile) throw new UserException("Fichier trop volumineux.");
            string ext = Ext(path);
            ExtractResult r;
            switch (ext)
            {
                case "pdf": r = Pdf(path, progress); break;
                case "docx": case "docm": case "dotx": r = Docx(path); break;
                case "odt": case "ott": r = Odt(path); break;
                case "epub": r = Epub(path, progress); break;
                case "html": case "htm": case "xhtml":
                    r = WebExtractor.FromHtml(Decode(File.ReadAllBytes(path)), null);
                    r.Kind = "HTML";
                    break;
                case "rtf": r = Rtf(File.ReadAllBytes(path)); break;
                case "doc":
                    throw new UserException("L'ancien format Word .doc n'est pas pris en charge. Enregistre le document en .docx ou en PDF, puis rouvre-le.");
                default:
                    byte[] data = File.ReadAllBytes(path);
                    if (LooksBinary(data))
                    {
                        if (data.Length > 4 && data[0] == '%' && data[1] == 'P' && data[2] == 'D' && data[3] == 'F') { r = Pdf(path, progress); break; }
                        throw new UserException("Ce type de fichier n'est pas pris en charge.");
                    }
                    r = PlainText(Decode(data), ext == "md");
                    r.Kind = ext == "md" ? "MARKDOWN" : "TEXTE";
                    break;
            }
            if (string.IsNullOrWhiteSpace(r.Title)) r.Title = Path.GetFileNameWithoutExtension(path);
            return Finish(r);
        }

        public static ExtractResult FromText(string title, string text)
        {
            var r = PlainText(text, false);
            r.Kind = "TEXTE";
            r.Title = title;
            return Finish(r);
        }

        // ------------------------------------------------------------------ PDF

        static ExtractResult Pdf(string path, Action<string> progress)
        {
            var r = new ExtractResult { Kind = "PDF" };
            PdfDocument doc;
            try
            {
                doc = PdfDocument.Open(path);
            }
            catch (Exception e) when (e.GetType().Name.Contains("Encrypted"))
            {
                throw new UserException("Ce PDF est protégé par un mot de passe.");
            }
            using (doc)
            {
                string t = doc.Information?.Title;
                if (!string.IsNullOrWhiteSpace(t) && t.Trim().Length > 2) r.Title = t.Trim();
                int pages = doc.NumberOfPages;
                var pageBlocks = new List<List<string>>();
                for (int i = 1; i <= pages; i++)
                {
                    if (progress != null && (i == 1 || i % 5 == 0)) progress("Lecture du PDF : page " + i + " / " + pages);
                    Page page = doc.GetPage(i);
                    pageBlocks.Add(PageBlocks(page));
                }
                RemoveRepeatedHeaders(pageBlocks);
                var blocks = new List<string>();
                foreach (var pb0 in pageBlocks)
                {
                    var pb = pb0;
                    // Paragraphe coupé par un changement de page : on recolle les deux morceaux.
                    if (blocks.Count > 0 && pb.Count > 0)
                    {
                        string last = blocks[blocks.Count - 1], first = pb[0];
                        if (!EndsSentence(last) && char.IsLower(first[0]))
                        {
                            blocks[blocks.Count - 1] = JoinLines(last, first);
                            pb = pb.Skip(1).ToList();
                        }
                    }
                    blocks.AddRange(pb);
                }
                foreach (var b in blocks) AddPara(r.Paragraphs, b);
            }
            if (CountChars(r.Paragraphs) < 20)
                throw new NeedsOcrException("Ce PDF ne contient pas de texte : c'est un document scanné (des images).");
            return r;
        }

        /// <summary>Blocs de texte d'une page dans l'ordre de lecture (colonnes comprises).</summary>
        static List<string> PageBlocks(Page page)
        {
            var output = new List<string>();
            var words = NearestNeighbourWordExtractor.Instance.GetWords(page.Letters).ToList();
            if (words.Count == 0) return output;
            var blocks = DocstrumBoundingBoxes.Instance.GetBlocks(words);
            var ordered = UnsupervisedReadingOrderDetector.Instance.Get(blocks);
            foreach (var block in ordered)
            {
                var lines = block.TextLines.Select(l => l.Text.Trim()).Where(l => l.Length > 0).ToList();
                if (lines.Count == 0) continue;
                int maxLen = lines.Max(l => l.Length);
                string cur = null, prev = null;
                foreach (var l in lines)
                {
                    if (cur == null) { cur = prev = l; continue; }
                    // Nouveau paragraphe : ligne précédente courte (fin de paragraphe ou titre) suivie d'une majuscule, ou puce.
                    bool prevShort = prev.Length < maxLen * 0.7;
                    bool startsUpper = char.IsUpper(l[0]) || char.IsDigit(l[0]);
                    bool bullet = Regex.IsMatch(l, @"^[\u2022\u25AA\u25CF\u2013\u2014\uF0B7*-]\s");
                    if (bullet || (prevShort && startsUpper && maxLen > 30))
                    {
                        if (!IsPageNumber(cur)) output.Add(cur);
                        cur = l;
                    }
                    else cur = JoinLines(cur, l);
                    prev = l;
                }
                if (cur != null && !IsPageNumber(cur)) output.Add(cur);
            }
            return output;
        }

        public static bool EndsSentence(string s)
        {
            if (s.Length == 0) return true;
            char ch = s[s.Length - 1];
            return ch == '.' || ch == '!' || ch == '?' || ch == ':' || ch == '»' || ch == '"' || ch == ';' || ch == '…';
        }

        static bool IsPageNumber(string p) =>
            Regex.IsMatch(p, @"^(page\s*)?[-–]?\s*\d{1,4}\s*[-–]?(\s*(/|sur|of)\s*\d{1,4})?$", RegexOptions.IgnoreCase);

        /// <summary>« prob- » + « lème » donne « problème » ; sinon on recolle avec un espace.</summary>
        public static string JoinLines(string a, string b)
        {
            int n = a.Length;
            if (n > 1 && a[n - 1] == '-' && char.IsLetter(a[n - 2]) && b.Length > 0 && char.IsLower(b[0]))
                return a.Substring(0, n - 1) + b;
            return a + " " + b;
        }

        static void RemoveRepeatedHeaders(List<List<string>> pages)
        {
            if (pages.Count < 3) return;
            var count = new Dictionary<string, int>();
            foreach (var pb in pages)
            {
                var seen = new HashSet<string>();
                for (int i = 0; i < pb.Count; i++)
                {
                    if (i > 1 && i < pb.Count - 2) continue;
                    string k = HeaderKey(pb[i]);
                    if (k.Length > 0 && k.Length < 120 && seen.Add(k)) count[k] = count.TryGetValue(k, out int c) ? c + 1 : 1;
                }
            }
            int limit = Math.Max(3, pages.Count / 2);
            for (int p = 0; p < pages.Count; p++)
            {
                var pb = pages[p];
                int n = pb.Count;
                for (int i = n - 1; i >= 0; i--)
                {
                    if (i > 1 && i < n - 2) continue;
                    if (count.TryGetValue(HeaderKey(pb[i]), out int c) && c >= limit) pb.RemoveAt(i);
                }
            }
        }

        static string HeaderKey(string s) => Regex.Replace(s, @"\d+", "#").Trim().ToLowerInvariant();

        /// <summary>Texte reconnu (photo) : lignes recollées en paragraphes, mots coupés réparés.</summary>
        public static List<string> OcrParagraphs(IEnumerable<List<string>> paragraphsOfLines)
        {
            var blocks = new List<string>();
            foreach (var lines in paragraphsOfLines)
            {
                string cur = null;
                foreach (var l0 in lines)
                {
                    string l = l0.Trim();
                    if (l.Length == 0) continue;
                    cur = cur == null ? l : JoinLines(cur, l);
                }
                if (cur == null) continue;
                if (blocks.Count > 0 && !EndsSentence(blocks[blocks.Count - 1]) && char.IsLower(cur[0]))
                    blocks[blocks.Count - 1] = JoinLines(blocks[blocks.Count - 1], cur);
                else blocks.Add(cur);
            }
            var output = new List<string>();
            foreach (var b in blocks) AddPara(output, b);
            return output;
        }

        // ------------------------------------------------------------------ Word, OpenOffice

        static ExtractResult Docx(string path)
        {
            var r = new ExtractResult { Kind = "WORD" };
            using (var zip = ZipFile.OpenRead(path))
            {
                var e = zip.GetEntry("word/document.xml") ?? throw new UserException("Document Word invalide.");
                r.Title = CoreTitle(zip, "docProps/core.xml");
                using (var s = e.Open())
                using (var xr = XmlReader.Create(s, new XmlReaderSettings { DtdProcessing = DtdProcessing.Ignore }))
                {
                    var para = new StringBuilder();
                    bool inText = false;
                    while (xr.Read())
                    {
                        if (xr.NodeType == XmlNodeType.Element)
                        {
                            string n = xr.LocalName;
                            if (n == "t" && !xr.IsEmptyElement) inText = true;
                            else if (n == "tab" || n == "br" || n == "cr") para.Append(' ');
                            else if (n == "noBreakHyphen") para.Append('-');
                            else if (n == "p" && xr.IsEmptyElement) { AddPara(r.Paragraphs, para.ToString()); para.Clear(); }
                        }
                        else if (xr.NodeType == XmlNodeType.EndElement)
                        {
                            if (xr.LocalName == "t") inText = false;
                            else if (xr.LocalName == "p") { AddPara(r.Paragraphs, para.ToString()); para.Clear(); }
                        }
                        else if ((xr.NodeType == XmlNodeType.Text || xr.NodeType == XmlNodeType.SignificantWhitespace || xr.NodeType == XmlNodeType.Whitespace) && inText)
                        {
                            para.Append(xr.Value);
                        }
                    }
                    AddPara(r.Paragraphs, para.ToString());
                }
            }
            return r;
        }

        static ExtractResult Odt(string path)
        {
            var r = new ExtractResult { Kind = "ODT" };
            using (var zip = ZipFile.OpenRead(path))
            {
                var e = zip.GetEntry("content.xml") ?? throw new UserException("Document OpenOffice invalide.");
                r.Title = CoreTitle(zip, "meta.xml");
                using (var s = e.Open())
                using (var xr = XmlReader.Create(s, new XmlReaderSettings { DtdProcessing = DtdProcessing.Ignore }))
                {
                    var para = new StringBuilder();
                    int depth = 0;
                    bool inNote = false;
                    while (xr.Read())
                    {
                        if (xr.NodeType == XmlNodeType.Element)
                        {
                            string n = xr.LocalName;
                            if ((n == "p" || n == "h") && xr.Prefix == "text")
                            {
                                if (depth > 0) { AddPara(r.Paragraphs, para.ToString()); para.Clear(); }
                                if (!xr.IsEmptyElement) depth++;
                            }
                            else if (n == "note") { if (!xr.IsEmptyElement) inNote = true; }
                            else if (n == "s" || n == "tab" || n == "line-break") para.Append(' ');
                        }
                        else if (xr.NodeType == XmlNodeType.EndElement)
                        {
                            string n = xr.LocalName;
                            if ((n == "p" || n == "h") && xr.Prefix == "text")
                            {
                                depth--;
                                AddPara(r.Paragraphs, para.ToString());
                                para.Clear();
                            }
                            else if (n == "note") inNote = false;
                        }
                        else if ((xr.NodeType == XmlNodeType.Text || xr.NodeType == XmlNodeType.SignificantWhitespace) && depth > 0 && !inNote)
                        {
                            para.Append(xr.Value);
                        }
                    }
                }
            }
            return r;
        }

        static string CoreTitle(ZipArchive zip, string entry)
        {
            try
            {
                var e = zip.GetEntry(entry);
                if (e == null) return null;
                using (var s = e.Open())
                {
                    var x = XDocument.Load(s);
                    var t = x.Descendants().FirstOrDefault(el => el.Name.LocalName == "title");
                    string v = t?.Value.Trim();
                    return string.IsNullOrEmpty(v) ? null : v;
                }
            }
            catch
            {
                return null;
            }
        }

        // ------------------------------------------------------------------ EPUB

        static ExtractResult Epub(string path, Action<string> progress)
        {
            var r = new ExtractResult { Kind = "EPUB" };
            using (var zip = ZipFile.OpenRead(path))
            {
                var ce = zip.GetEntry("META-INF/container.xml") ?? throw new UserException("Livre EPUB invalide.");
                XDocument container;
                using (var s = ce.Open()) container = XDocument.Load(s);
                var rootfile = container.Descendants().FirstOrDefault(e => e.Name.LocalName == "rootfile") ?? throw new UserException("Livre EPUB invalide.");
                string opfPath = (string)rootfile.Attribute("full-path") ?? "";
                string baseDir = opfPath.Contains("/") ? opfPath.Substring(0, opfPath.LastIndexOf('/') + 1) : "";
                var oe = zip.GetEntry(opfPath) ?? throw new UserException("Livre EPUB invalide.");
                XDocument opf;
                using (var s = oe.Open()) opf = XDocument.Load(s);
                var title = opf.Descendants().FirstOrDefault(e => e.Name.LocalName == "title");
                if (title != null && title.Value.Trim().Length > 0) r.Title = title.Value.Trim();
                var hrefs = opf.Descendants().Where(e => e.Name.LocalName == "item")
                    .Where(e => e.Attribute("id") != null && e.Attribute("href") != null)
                    .GroupBy(e => (string)e.Attribute("id")).ToDictionary(g => g.Key, g => (string)g.First().Attribute("href"));
                var spine = opf.Descendants().Where(e => e.Name.LocalName == "itemref").ToList();
                int i = 0;
                foreach (var item in spine)
                {
                    i++;
                    progress?.Invoke("Lecture du livre : chapitre " + i + " / " + spine.Count);
                    string idref = (string)item.Attribute("idref");
                    if (idref == null || !hrefs.TryGetValue(idref, out string href)) continue;
                    string p = NormalizePath(baseDir + Uri.UnescapeDataString(href));
                    var xe = zip.GetEntry(p);
                    if (xe == null) continue;
                    string html;
                    using (var s = xe.Open())
                    using (var ms = new MemoryStream())
                    {
                        s.CopyTo(ms);
                        html = Decode(ms.ToArray());
                    }
                    var hd = new HtmlAgilityPack.HtmlDocument();
                    hd.LoadHtml(html);
                    var body = hd.DocumentNode.SelectSingleNode("//body") ?? hd.DocumentNode;
                    WebExtractor.CollectBlocks(body, r.Paragraphs);
                }
            }
            if (r.Paragraphs.Count == 0) throw new UserException("Ce livre ne contient pas de texte lisible.");
            return r;
        }

        static string NormalizePath(string p)
        {
            var parts = new List<string>();
            foreach (var s in p.Split('/'))
            {
                if (s == "..") { if (parts.Count > 0) parts.RemoveAt(parts.Count - 1); }
                else if (s.Length > 0 && s != ".") parts.Add(s);
            }
            return string.Join("/", parts);
        }

        // ------------------------------------------------------------------ RTF

        static ExtractResult Rtf(byte[] data)
        {
            string s = Encoding.GetEncoding(28591).GetString(data);
            var output = new StringBuilder();
            var cp = Encoding.GetEncoding(1252);
            int depth = 0, skipDepth = -1, ucSkip = 1, pendingSkip = 0, i = 0, n = s.Length;
            var skipWords = new HashSet<string> { "fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "object", "themedata", "datastore", "latentstyles", "listtable", "listoverridetable", "rsidtbl", "generator" };
            while (i < n)
            {
                char ch = s[i];
                if (ch == '{') { depth++; i++; continue; }
                if (ch == '}') { if (depth == skipDepth) skipDepth = -1; depth--; i++; continue; }
                bool skipping = skipDepth >= 0 && depth >= skipDepth;
                if (ch == '\\')
                {
                    if (i + 1 >= n) break;
                    char nx = s[i + 1];
                    if (nx == '\\' || nx == '{' || nx == '}') { if (!skipping) output.Append(nx); i += 2; continue; }
                    if (nx == '\'')
                    {
                        if (i + 3 < n && !skipping)
                        {
                            if (pendingSkip > 0) pendingSkip--;
                            else
                            {
                                try { output.Append(cp.GetString(new[] { Convert.ToByte(s.Substring(i + 2, 2), 16) })); } catch { }
                            }
                        }
                        i += 4;
                        continue;
                    }
                    if (nx == '*') { if (skipDepth < 0) skipDepth = depth; i += 2; continue; }
                    if (nx == '~') { if (!skipping) output.Append(' '); i += 2; continue; }
                    if (nx == '-' || nx == '_') { i += 2; continue; }
                    int j = i + 1;
                    while (j < n && char.IsLetter(s[j])) j++;
                    string word = s.Substring(i + 1, j - i - 1);
                    int k = j;
                    if (k < n && (s[k] == '-' || char.IsDigit(s[k]))) { k++; while (k < n && char.IsDigit(s[k])) k++; }
                    string param = s.Substring(j, k - j);
                    if (k < n && s[k] == ' ') k++;
                    i = k;
                    if (word.Length == 0) { i = j + 1; continue; }
                    if (skipWords.Contains(word)) { if (skipDepth < 0) skipDepth = depth; continue; }
                    if (skipping) continue;
                    switch (word)
                    {
                        case "par": case "line": case "sect": case "page": case "row": output.Append('\n'); break;
                        case "tab": case "cell": output.Append(' '); break;
                        case "uc": int.TryParse(param, out ucSkip); break;
                        case "u":
                            if (int.TryParse(param, out int v)) { if (v < 0) v += 65536; output.Append((char)v); pendingSkip = ucSkip; }
                            break;
                        case "emdash": output.Append('—'); break;
                        case "endash": output.Append('–'); break;
                        case "lquote": case "rquote": output.Append('\''); break;
                        case "ldblquote": case "rdblquote": output.Append('"'); break;
                    }
                    continue;
                }
                if (ch == '\r' || ch == '\n') { i++; continue; }
                if (!skipping)
                {
                    if (pendingSkip > 0) pendingSkip--;
                    else output.Append(ch);
                }
                i++;
            }
            var r = new ExtractResult { Kind = "RTF" };
            foreach (var line in output.ToString().Split('\n')) AddPara(r.Paragraphs, line);
            return r;
        }

        // ------------------------------------------------------------------ texte brut

        public static ExtractResult PlainText(string text, bool markdown)
        {
            var r = new ExtractResult();
            text = text.Replace("\r\n", "\n").Replace('\r', '\n');
            if (text.Length > 0 && text[0] == '﻿') text = text.Substring(1);
            string[] lines = text.Split('\n');
            int blank = lines.Count(l => l.Trim().Length == 0), nonBlank = lines.Length - blank;
            // Texte à l'ancienne : lignes coupées à ~70 caractères, paragraphes séparés par une ligne vide.
            bool wrapped = blank > 0 && nonBlank > blank * 2;
            var para = new StringBuilder();
            foreach (var raw in lines)
            {
                string l = raw.Trim();
                if (markdown) l = CleanMarkdown(l);
                if (l.Length == 0)
                {
                    AddPara(r.Paragraphs, para.ToString());
                    para.Clear();
                    continue;
                }
                if (wrapped)
                {
                    if (para.Length > 0) para.Append(' ');
                    para.Append(l);
                }
                else AddPara(r.Paragraphs, l);
            }
            AddPara(r.Paragraphs, para.ToString());
            return r;
        }

        static string CleanMarkdown(string l)
        {
            l = Regex.Replace(l, @"^#{1,6}\s+", "");
            l = Regex.Replace(l, @"^[-*+]\s+", "");
            l = Regex.Replace(l, @"^>\s?", "");
            l = Regex.Replace(l, @"!\[([^\]]*)\]\([^)]*\)", "$1");
            l = Regex.Replace(l, @"\[([^\]]*)\]\([^)]*\)", "$1");
            l = Regex.Replace(l, @"[*_`]{1,3}", "");
            if (Regex.IsMatch(l, @"^[-=*_\s|:]+$")) return "";
            return l.Trim();
        }

        // ------------------------------------------------------------------ utilitaires

        public static void AddPara(List<string> output, string p)
        {
            if (p == null) return;
            p = p.Replace(' ', ' ').Replace('​', ' ');
            p = Regex.Replace(p, "[-]", " ");  // symboles des polices Symbol/Wingdings
            p = Regex.Replace(p, @"\s+", " ").Trim();
            // Puces de liste en début de ligne : inutile de les prononcer.
            p = Regex.Replace(p, "^[•·▪◦●○■➤►–—*]+\\s+", "");
            if (p.Length == 0) return;
            if (!p.Any(char.IsLetterOrDigit)) return;
            output.Add(p);
        }

        /// <summary>Découpe les paragraphes géants et nettoie le titre.</summary>
        public static ExtractResult Finish(ExtractResult r)
        {
            var output = new List<string>();
            foreach (var p in r.Paragraphs)
            {
                if (p.Length <= 1500) { output.Add(p); continue; }
                var sb = new StringBuilder();
                foreach (var s in Sentences.Split(p))
                {
                    if (sb.Length + s.Length > 1200 && sb.Length > 0) { output.Add(sb.ToString().Trim()); sb.Clear(); }
                    sb.Append(s).Append(' ');
                }
                if (sb.ToString().Trim().Length > 0) output.Add(sb.ToString().Trim());
            }
            r.Paragraphs = output;
            if (string.IsNullOrWhiteSpace(r.Title)) r.Title = output.Count == 0 ? "Sans titre" : output[0];
            r.Title = Regex.Replace(r.Title, @"\s+", " ").Trim();
            if (r.Title.Length > 120) r.Title = r.Title.Substring(0, 117) + "…";
            return r;
        }

        public static int CountChars(List<string> l) => l.Sum(s => s.Length);

        static bool LooksBinary(byte[] d)
        {
            int n = Math.Min(d.Length, 8192);
            if (n >= 2 && ((d[0] == 0xFF && d[1] == 0xFE) || (d[0] == 0xFE && d[1] == 0xFF))) return false;
            for (int i = 0; i < n; i++) if (d[i] == 0) return true;
            return false;
        }

        /// <summary>Décode en UTF-8 si c'est valide, sinon en Windows-1252.</summary>
        public static string Decode(byte[] d)
        {
            if (d.Length >= 2 && d[0] == 0xFF && d[1] == 0xFE) return Encoding.Unicode.GetString(d, 2, d.Length - 2);
            if (d.Length >= 2 && d[0] == 0xFE && d[1] == 0xFF) return Encoding.BigEndianUnicode.GetString(d, 2, d.Length - 2);
            try
            {
                return new UTF8Encoding(false, true).GetString(d);
            }
            catch (DecoderFallbackException)
            {
                return Encoding.GetEncoding(1252).GetString(d);
            }
        }
    }
}
