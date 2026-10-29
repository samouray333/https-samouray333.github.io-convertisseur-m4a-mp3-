using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Text;

namespace Lisys
{
    /// <summary>
    /// Bibliothèque locale : chaque document lu est gardé (texte extrait + position de lecture)
    /// dans %APPDATA%\Lisys, pour reprendre là où on s'était arrêté.
    /// </summary>
    public static class Library
    {
        const int MaxEntries = 60;
        static readonly object Lock = new object();

        [DataContract]
        public sealed class Entry
        {
            [DataMember] public string Id;
            [DataMember] public string Title;
            [DataMember] public string Source;
            [DataMember] public string Kind;
            [DataMember] public int Para;
            [DataMember] public int Sentence;
            [DataMember] public int ParaCount;
            [DataMember] public long Opened;

            public int Percent => ParaCount <= 1 ? (Para > 0 ? 100 : 0) : Math.Min(100, (int)Math.Round(100.0 * Para / (ParaCount - 1)));

            public DateTime OpenedDate => DateTimeOffset.FromUnixTimeMilliseconds(Opened).LocalDateTime;
        }

        static string DocsDir
        {
            get
            {
                string d = Path.Combine(Settings.Folder, "docs");
                Directory.CreateDirectory(d);
                return d;
            }
        }

        static string IndexPath => Path.Combine(Settings.Folder, "bibliotheque.json");

        public static string MakeId(string source, string title)
        {
            using (var sha = SHA1.Create())
            {
                byte[] h = sha.ComputeHash(Encoding.UTF8.GetBytes(source + "|" + title));
                var sb = new StringBuilder();
                for (int i = 0; i < 10; i++) sb.Append(h[i].ToString("x2"));
                return sb.ToString();
            }
        }

        public static List<Entry> List()
        {
            lock (Lock)
            {
                try
                {
                    if (!File.Exists(IndexPath)) return new List<Entry>();
                    using (var fs = File.OpenRead(IndexPath))
                    {
                        var l = (List<Entry>)new DataContractJsonSerializer(typeof(List<Entry>)).ReadObject(fs);
                        return l ?? new List<Entry>();
                    }
                }
                catch
                {
                    return new List<Entry>();
                }
            }
        }

        static void SaveList(List<Entry> list)
        {
            try
            {
                string tmp = IndexPath + ".tmp";
                using (var fs = File.Create(tmp))
                {
                    new DataContractJsonSerializer(typeof(List<Entry>)).WriteObject(fs, list);
                }
                if (File.Exists(IndexPath)) File.Delete(IndexPath);
                File.Move(tmp, IndexPath);
            }
            catch
            {
            }
        }

        public static Entry Get(string id)
        {
            return List().FirstOrDefault(e => e.Id == id);
        }

        /// <summary>Enregistre un document extrait. Si on l'a déjà lu, on garde la position de lecture.</summary>
        public static Entry Add(ExtractResult r, string source)
        {
            lock (Lock)
            {
                string id = MakeId(source, r.Title);
                var list = List();
                var existing = list.FirstOrDefault(e => e.Id == id);
                if (existing != null) list.Remove(existing);
                var entry = existing ?? new Entry();
                entry.Id = id;
                entry.Title = r.Title;
                entry.Source = source;
                entry.Kind = r.Kind;
                if (existing == null || existing.ParaCount != r.Paragraphs.Count)
                {
                    entry.Para = 0;
                    entry.Sentence = 0;
                }
                entry.ParaCount = r.Paragraphs.Count;
                entry.Opened = DateTimeOffset.Now.ToUnixTimeMilliseconds();
                list.Insert(0, entry);
                while (list.Count > MaxEntries)
                {
                    var old = list[list.Count - 1];
                    list.RemoveAt(list.Count - 1);
                    TryDelete(Path.Combine(DocsDir, old.Id + ".txt"));
                }
                File.WriteAllLines(Path.Combine(DocsDir, id + ".txt"), r.Paragraphs.Select(p => p.Replace('\n', ' ').Replace('\r', ' ')), Encoding.UTF8);
                SaveList(list);
                return entry;
            }
        }

        public static void Touch(string id)
        {
            lock (Lock)
            {
                var list = List();
                var e = list.FirstOrDefault(x => x.Id == id);
                if (e == null) return;
                e.Opened = DateTimeOffset.Now.ToUnixTimeMilliseconds();
                list.Remove(e);
                list.Insert(0, e);
                SaveList(list);
            }
        }

        public static void SavePosition(string id, int para, int sentence)
        {
            lock (Lock)
            {
                var list = List();
                var e = list.FirstOrDefault(x => x.Id == id);
                if (e == null || (e.Para == para && e.Sentence == sentence)) return;
                e.Para = para;
                e.Sentence = sentence;
                SaveList(list);
            }
        }

        public static void Remove(string id)
        {
            lock (Lock)
            {
                var list = List();
                list.RemoveAll(x => x.Id == id);
                TryDelete(Path.Combine(DocsDir, id + ".txt"));
                SaveList(list);
            }
        }

        public static void Clear()
        {
            lock (Lock)
            {
                foreach (var e in List()) TryDelete(Path.Combine(DocsDir, e.Id + ".txt"));
                SaveList(new List<Entry>());
            }
        }

        public static List<string> LoadParagraphs(string id)
        {
            string f = Path.Combine(DocsDir, id + ".txt");
            if (!File.Exists(f)) return new List<string>();
            return File.ReadAllLines(f, Encoding.UTF8).Where(l => l.Length > 0).ToList();
        }

        static void TryDelete(string f)
        {
            try { if (File.Exists(f)) File.Delete(f); } catch { }
        }
    }
}
