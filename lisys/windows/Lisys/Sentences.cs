using System;
using System.Collections.Generic;

namespace Lisys
{
    /// <summary>Découpage en phrases, pour lire et surligner phrase par phrase.</summary>
    public static class Sentences
    {
        const int MaxLen = 320;

        static readonly HashSet<string> Abbreviations = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "M", "MM", "Mme", "Mmes", "Mlle", "Mlles", "Dr", "Pr", "Me", "Mgr", "St", "Ste", "p", "pp", "cf",
            "av", "bd", "n°", "no", "vol", "ch", "art", "fig", "env", "ex", "tél", "tel", "réf", "ref", "approx",
            "Mr", "Mrs", "Ms", "Jr", "Sr", "vs", "etc."
        };

        /// <summary>Renvoie les phrases avec leurs positions [début, fin[ dans le paragraphe.</summary>
        public static List<int[]> Bounds(string p)
        {
            var raw = new List<int[]>();
            int start = 0, n = p.Length;
            for (int i = 0; i < n; i++)
            {
                char c = p[i];
                if (c != '.' && c != '!' && c != '?' && c != '…') continue;
                int j = i + 1;
                while (j < n && (p[j] == '.' || p[j] == '!' || p[j] == '?' || p[j] == '…')) j++;
                while (j < n && (p[j] == '»' || p[j] == '"' || p[j] == '\'' || p[j] == ')' || p[j] == ']' || p[j] == '”' || p[j] == '’')) j++;
                if (j < n && !char.IsWhiteSpace(p[j])) { i = j - 1; continue; }
                int k = j;
                while (k < n && char.IsWhiteSpace(p[k])) k++;
                // Typographie française : « Bonjour ! » Puis… (espace avant le guillemet fermant)
                while (k < n && (p[k] == '»' || p[k] == '”'))
                {
                    k++;
                    while (k < n && char.IsWhiteSpace(p[k])) k++;
                }
                if (k < n)
                {
                    char next = p[k];
                    bool startsNew = char.IsUpper(next) || char.IsDigit(next) || next == '«' || next == '"' || next == '“'
                                     || next == '-' || next == '—' || next == '(' || next == '¿' || next == '¡';
                    if (!startsNew) { i = j - 1; continue; }
                    if (c == '.' && IsAbbreviation(p, start, i)) { i = j - 1; continue; }
                }
                raw.Add(new[] { start, k });
                start = k;
                i = k - 1;
            }
            if (start < n) raw.Add(new[] { start, n });
            if (raw.Count == 0) raw.Add(new[] { 0, n });

            // Recolle les morceaux trop courts à la phrase suivante.
            var merged = new List<int[]>();
            foreach (var b in raw)
            {
                if (merged.Count > 0)
                {
                    var last = merged[merged.Count - 1];
                    if (p.Substring(last[0], last[1] - last[0]).Trim().Length <= 4) { last[1] = b[1]; continue; }
                }
                merged.Add(new[] { b[0], b[1] });
            }

            var output = new List<int[]>();
            foreach (var b in merged) SplitLong(p, b[0], b[1], output);
            return output;
        }

        public static List<string> Split(string p)
        {
            var l = new List<string>();
            foreach (var b in Bounds(p)) l.Add(p.Substring(b[0], b[1] - b[0]));
            return l;
        }

        static bool IsAbbreviation(string p, int sentenceStart, int dot)
        {
            int w = dot - 1;
            while (w >= sentenceStart && !char.IsWhiteSpace(p[w]) && p[w] != '(') w--;
            string word = p.Substring(w + 1, dot - w - 1);
            if (word.Length == 0) return false;
            if (word.Length == 1 && char.IsUpper(word[0])) return true; // initiale : « J. Martin »
            return Abbreviations.Contains(word);
        }

        static void SplitLong(string p, int start, int end, List<int[]> output)
        {
            while (end - start > MaxLen)
            {
                int cut = -1;
                for (int i = start + MaxLen; i > start + MaxLen / 3; i--)
                {
                    char c = p[i];
                    if (c == ',' || c == ';' || c == ':' || c == ')' || c == '—') { cut = i + 1; break; }
                }
                if (cut < 0)
                {
                    for (int i = start + MaxLen; i > start + MaxLen / 3; i--)
                        if (p[i] == ' ') { cut = i + 1; break; }
                }
                if (cut < 0) cut = start + MaxLen;
                output.Add(new[] { start, cut });
                start = cut;
            }
            if (end > start) output.Add(new[] { start, end });
        }
    }
}
