using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Speech.Synthesis;
using System.Threading;
using System.Windows.Forms;

namespace Lisys
{
    /// <summary>
    /// Moteur de lecture à voix haute (synthèse vocale de Windows), phrase par phrase,
    /// avec la position du mot prononcé pour le surlignage.
    /// </summary>
    public sealed class ReaderEngine : IDisposable
    {
        readonly SpeechSynthesizer synth;
        readonly SynchronizationContext ui;
        readonly System.Windows.Forms.Timer pauseTimer = new System.Windows.Forms.Timer();
        readonly List<List<int[]>> sentCache = new List<List<int[]>>();
        System.Speech.Synthesis.Prompt current;
        int currentPara, currentSent;
        long lastSave;

        public string DocId { get; private set; }
        public string Title { get; private set; } = "";
        public List<string> Paragraphs { get; private set; } = new List<string>();
        public int Para { get; private set; }
        public int Sentence { get; private set; }
        public bool Playing { get; private set; }
        public string Error { get; private set; }

        /// <summary>Paragraphe et phrase en cours.</summary>
        public event Action<int, int> PositionChanged;
        /// <summary>Paragraphe, début et fin du mot prononcé (dans le paragraphe).</summary>
        public event Action<int, int, int> WordChanged;
        public event Action<bool> StateChanged;
        public event Action Finished;
        public event Action DocumentChanged;

        public ReaderEngine()
        {
            ui = SynchronizationContext.Current ?? new WindowsFormsSynchronizationContext();
            try
            {
                synth = new SpeechSynthesizer();
                synth.SetOutputToDefaultAudioDevice();
                synth.SpeakProgress += OnProgress;
                synth.SpeakCompleted += OnCompleted;
                ApplySettings();
            }
            catch (Exception e)
            {
                synth = null;
                Error = "La synthèse vocale de Windows n'est pas disponible (" + e.Message + ").";
            }
            pauseTimer.Interval = 320;
            pauseTimer.Tick += (s, e) => { pauseTimer.Stop(); if (Playing) SpeakCurrent(); };
        }

        public void Dispose()
        {
            pauseTimer.Dispose();
            try { synth?.SpeakAsyncCancelAll(); synth?.Dispose(); } catch { }
        }

        // ------------------------------------------------------------------ voix et vitesse

        /// <summary>Vitesse 0,5× à 3× convertie en vitesse SAPI (-10 à 10, environ ×3 aux extrêmes).</summary>
        public static int SapiRate(double factor)
        {
            factor = Math.Max(0.34, Math.Min(3.0, factor));
            return Math.Max(-10, Math.Min(10, (int)Math.Round(10 * Math.Log(factor) / Math.Log(3))));
        }

        public void ApplySettings()
        {
            if (synth == null) return;
            var s = Settings.Current;
            try { synth.Rate = SapiRate(s.Rate); } catch { }
            try { synth.Volume = Math.Max(0, Math.Min(100, s.Volume)); } catch { }
            ApplyVoice(synth, s.Voice);
        }

        public static void ApplyVoice(SpeechSynthesizer synth, string wanted)
        {
            var voices = synth.GetInstalledVoices().Where(v => v.Enabled).Select(v => v.VoiceInfo).ToList();
            var v1 = voices.FirstOrDefault(v => v.Name == wanted)
                     ?? voices.FirstOrDefault(v => v.Culture != null && v.Culture.TwoLetterISOLanguageName == "fr");
            if (v1 != null)
            {
                try { synth.SelectVoice(v1.Name); } catch { }
            }
        }

        public List<VoiceInfo> Voices()
        {
            if (synth == null) return new List<VoiceInfo>();
            return synth.GetInstalledVoices().Where(v => v.Enabled).Select(v => v.VoiceInfo)
                .OrderBy(v => v.Culture != null && v.Culture.TwoLetterISOLanguageName == "fr" ? 0 : 1)
                .ThenBy(v => v.Culture?.Name).ThenBy(v => v.Name).ToList();
        }

        public string CurrentVoiceName => synth?.Voice?.Name;

        public void SetRate(double factor)
        {
            Settings.Current.Rate = factor;
            Settings.Current.Save();
            if (synth != null) synth.Rate = SapiRate(factor);
            if (Playing) Restart();
        }

        public void SetVoice(string name)
        {
            Settings.Current.Voice = name ?? "";
            Settings.Current.Save();
            if (synth == null) return;
            ApplyVoice(synth, name);
            if (Playing) Restart();
        }

        public void Preview(string text)
        {
            if (synth == null || Playing) return;
            synth.SpeakAsyncCancelAll();
            current = null;
            synth.SpeakAsync(text);
        }

        // ------------------------------------------------------------------ document

        public void Load(string id, bool force = false)
        {
            if (id == DocId && !force) return;
            if (Playing) Pause();
            SavePosition(true);
            var e = Library.Get(id);
            DocId = id;
            Title = e?.Title ?? "";
            SetParagraphs(Library.LoadParagraphs(id));
            Para = Sentence = 0;
            if (e != null && e.Para < Paragraphs.Count)
            {
                Para = Math.Max(0, e.Para);
                Sentence = Math.Max(0, Math.Min(e.Sentence, Sentences(Para).Count - 1));
            }
            DocumentChanged?.Invoke();
        }

        /// <summary>Texte lu à la volée (sous la souris, sélection) : pas enregistré dans la bibliothèque.</summary>
        public void LoadTransient(string title, List<string> paragraphs)
        {
            if (Playing) Pause();
            SavePosition(true);
            DocId = null;
            Title = title;
            SetParagraphs(paragraphs);
            Para = Sentence = 0;
            DocumentChanged?.Invoke();
        }

        void SetParagraphs(List<string> p)
        {
            Paragraphs = p;
            sentCache.Clear();
            for (int i = 0; i < p.Count; i++) sentCache.Add(null);
        }

        public List<int[]> Sentences(int p)
        {
            if (p < 0 || p >= Paragraphs.Count) return new List<int[]>();
            return sentCache[p] ?? (sentCache[p] = Lisys.Sentences.Bounds(Paragraphs[p]));
        }

        // ------------------------------------------------------------------ commandes

        public void Toggle()
        {
            if (Playing) Pause(); else Play();
        }

        public void Play()
        {
            if (synth == null || Paragraphs.Count == 0) return;
            if (Para >= Paragraphs.Count) { Para = 0; Sentence = 0; }
            Playing = true;
            StateChanged?.Invoke(true);
            SpeakCurrent();
        }

        public void Pause()
        {
            pauseTimer.Stop();
            if (!Playing) return;
            Playing = false;
            current = null;
            try { synth.SpeakAsyncCancelAll(); } catch { }
            SavePosition(true);
            StateChanged?.Invoke(false);
        }

        public void Next()
        {
            if (Paragraphs.Count == 0) return;
            int p = Para, s = Sentence + 1;
            if (s >= Sentences(p).Count) { p++; s = 0; }
            if (p >= Paragraphs.Count) return;
            Seek(p, s);
        }

        public void Previous()
        {
            if (Paragraphs.Count == 0) return;
            int p = Para, s = Sentence - 1;
            if (s < 0)
            {
                p--;
                if (p < 0) { p = 0; s = 0; }
                else s = Math.Max(0, Sentences(p).Count - 1);
            }
            Seek(p, s);
        }

        public void NextParagraph() { if (Para + 1 < Paragraphs.Count) Seek(Para + 1, 0); }

        public void PreviousParagraph()
        {
            if (Sentence > 0) Seek(Para, 0);
            else if (Para > 0) Seek(Para - 1, 0);
        }

        public void Seek(int p, int s)
        {
            if (Paragraphs.Count == 0) return;
            p = Math.Max(0, Math.Min(p, Paragraphs.Count - 1));
            s = Math.Max(0, Math.Min(s, Sentences(p).Count - 1));
            Para = p;
            Sentence = s;
            PositionChanged?.Invoke(Para, Sentence);
            if (Playing) Restart();
            SavePosition(false);
        }

        void Restart()
        {
            pauseTimer.Stop();
            current = null;
            try { synth.SpeakAsyncCancelAll(); } catch { }
            SpeakCurrent();
        }

        void SpeakCurrent()
        {
            if (synth == null || !Playing) return;
            var ss = Sentences(Para);
            if (Sentence >= ss.Count)
            {
                Finish();
                return;
            }
            var b = ss[Sentence];
            string text = Paragraphs[Para].Substring(b[0], b[1] - b[0]);
            currentPara = Para;
            currentSent = Sentence;
            PositionChanged?.Invoke(Para, Sentence);
            try
            {
                current = synth.SpeakAsync(text);
            }
            catch (Exception e)
            {
                Error = e.Message;
                Pause();
            }
        }

        void OnProgress(object sender, SpeakProgressEventArgs e)
        {
            if (e.Prompt != current) return;
            int p = currentPara, s = currentSent;
            var ss = Sentences(p);
            if (s >= ss.Count) return;
            int start = ss[s][0] + e.CharacterPosition;
            int end = start + e.CharacterCount;
            ui.Post(_ => { if (Playing && p == Para && s == Sentence) WordChanged?.Invoke(p, start, end); }, null);
        }

        void OnCompleted(object sender, SpeakCompletedEventArgs e)
        {
            if (e.Prompt != current || e.Cancelled) return;
            ui.Post(_ =>
            {
                if (!Playing || e.Prompt != current) return;
                current = null;
                var ss = Sentences(Para);
                bool endOfPara = Sentence + 1 >= ss.Count;
                if (endOfPara)
                {
                    if (Para + 1 >= Paragraphs.Count) { Finish(); return; }
                    Para++;
                    Sentence = 0;
                    SavePosition(false);
                    // Petite pause entre deux paragraphes, comme une vraie lecture.
                    pauseTimer.Start();
                    return;
                }
                Sentence++;
                SavePosition(false);
                SpeakCurrent();
            }, null);
        }

        void Finish()
        {
            Playing = false;
            current = null;
            Para = Math.Max(0, Paragraphs.Count - 1);
            Sentence = Math.Max(0, Sentences(Para).Count - 1);
            SavePosition(true);
            StateChanged?.Invoke(false);
            Finished?.Invoke();
        }

        void SavePosition(bool force)
        {
            if (DocId == null) return;
            long now = Environment.TickCount;
            if (!force && now - lastSave < 3000) return;
            lastSave = now;
            Library.SavePosition(DocId, Para, Sentence);
        }

        public static string VoiceLabel(VoiceInfo v)
        {
            string lang = v.Culture != null ? v.Culture.DisplayName : "";
            try { if (v.Culture != null) lang = new CultureInfo("fr-FR").TextInfo.ToTitleCase(v.Culture.NativeName); } catch { }
            return v.Name.Replace("Microsoft ", "").Replace(" Desktop", "") + (lang.Length > 0 ? "  (" + lang + ")" : "");
        }
    }
}
