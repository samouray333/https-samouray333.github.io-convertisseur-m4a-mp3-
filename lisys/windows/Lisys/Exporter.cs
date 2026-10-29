using System;
using System.IO;
using System.Linq;
using System.Speech.AudioFormat;
using System.Speech.Synthesis;
using System.Text.RegularExpressions;
using System.Threading;

namespace Lisys
{
    /// <summary>Transforme un document en fichier audio (.m4a, sinon .wav) dans Documents\Lisys.</summary>
    public static class Exporter
    {
        public static string Folder
        {
            get
            {
                string d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Lisys");
                Directory.CreateDirectory(d);
                return d;
            }
        }

        public static string SafeName(string t)
        {
            string s = Regex.Replace(t ?? "", @"[\\/:*?""<>|\p{Cc}]", " ");
            s = Regex.Replace(s, @"\s+", " ").Trim();
            if (s.Length > 80) s = s.Substring(0, 80).Trim();
            return s.Length == 0 ? "Lisys" : s;
        }

        /// <summary>À appeler hors du fil de l'interface. progress(fait, total).</summary>
        public static string Export(string docId, Action<int, int> progress, CancellationToken cancel)
        {
            var entry = Library.Get(docId);
            var paras = Library.LoadParagraphs(docId);
            if (paras.Count == 0) throw new UserException("Document vide.");
            string title = SafeName(entry?.Title);
            string wav = Path.Combine(Path.GetTempPath(), "lisys-export.wav");
            using (var synth = new SpeechSynthesizer())
            {
                ReaderEngine.ApplyVoice(synth, Settings.Current.Voice);
                synth.Rate = ReaderEngine.SapiRate(Settings.Current.Rate);
                synth.SetOutputToWaveFile(wav, new SpeechAudioFormatInfo(22050, AudioBitsPerSample.Sixteen, AudioChannel.Mono));
                for (int i = 0; i < paras.Count; i++)
                {
                    cancel.ThrowIfCancellationRequested();
                    progress?.Invoke(i, paras.Count);
                    var pb = new PromptBuilder();
                    pb.AppendText(paras[i]);
                    pb.AppendBreak(TimeSpan.FromMilliseconds(400));
                    synth.Speak(pb);
                }
                synth.SetOutputToNull();
            }
            progress?.Invoke(paras.Count, paras.Count);
            string m4a = Unique(Path.Combine(Folder, title + ".m4a"));
            try
            {
                NAudio.MediaFoundation.MediaFoundationApi.Startup();
                using (var reader = new NAudio.Wave.WaveFileReader(wav))
                {
                    NAudio.Wave.MediaFoundationEncoder.EncodeToAac(reader, m4a, 64000);
                }
                File.Delete(wav);
                return m4a;
            }
            catch
            {
                // Encodeur AAC absent (Windows N sans Media Feature Pack) : on garde le WAV.
                string w = Unique(Path.Combine(Folder, title + ".wav"));
                File.Move(wav, w);
                return w;
            }
        }

        static string Unique(string path)
        {
            if (!File.Exists(path)) return path;
            string dir = Path.GetDirectoryName(path), name = Path.GetFileNameWithoutExtension(path), ext = Path.GetExtension(path);
            for (int i = 2; ; i++)
            {
                string p = Path.Combine(dir, name + " (" + i + ")" + ext);
                if (!File.Exists(p)) return p;
            }
        }
    }
}
