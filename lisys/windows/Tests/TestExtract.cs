using System;
using System.Linq;
using Lisys;

// Tests sur PC (Mono ou Windows) des moteurs d'extraction de Lisys pour Windows.
static class TestExtract
{
    static int Main(string[] args)
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        int errors = 0;
        foreach (var a in args)
        {
            Console.WriteLine("==================== " + a);
            try
            {
                var t0 = DateTime.Now;
                var r = a.StartsWith("http") ? WebExtractor.FromUrl(a, null) : Extractor.FromFile(a, null);
                Console.WriteLine("Titre : " + r.Title + "   Type : " + r.Kind + "   Paragraphes : " + r.Paragraphs.Count + "   (" + (int)(DateTime.Now - t0).TotalMilliseconds + " ms)");
                for (int i = 0; i < Math.Min(12, r.Paragraphs.Count); i++)
                {
                    string p = r.Paragraphs[i];
                    Console.WriteLine("  [" + i + "] " + (p.Length > 200 ? p.Substring(0, 200) + "…" : p));
                    if (Environment.GetEnvironmentVariable("SENTENCES") == "1")
                        foreach (var s in Sentences.Split(p)) Console.WriteLine("       · " + s);
                }
            }
            catch (Exception e)
            {
                Console.WriteLine("ERREUR : " + e.GetType().Name + " : " + e.Message);
                errors++;
            }
        }
        return errors;
    }
}
