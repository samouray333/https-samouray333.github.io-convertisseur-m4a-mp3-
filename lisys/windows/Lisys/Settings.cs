using System;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace Lisys
{
    /// <summary>Réglages de Lisys, enregistrés dans %APPDATA%\Lisys\reglages.json.</summary>
    [DataContract]
    public sealed class Settings
    {
        public const int ThemeClair = 0, ThemeSombre = 1, ThemeContraste = 2, ThemeSepia = 3;

        [DataMember] public double Rate = 1.0;              // vitesse 0,5× à 3×
        [DataMember] public string Voice = "";              // vide = voix française par défaut
        [DataMember] public int Volume = 100;
        [DataMember] public int Theme = ThemeClair;
        [DataMember] public float TextSize = 22f;
        [DataMember] public bool BigMode;
        [DataMember] public bool FollowWord = true;
        [DataMember] public bool Caption;                   // bandeau en très gros texte
        [DataMember] public float CaptionSize = 34f;
        [DataMember] public int CaptionColors;
        [DataMember] public bool CaptionTop;
        [DataMember] public bool Hotkeys = true;            // raccourcis clavier dans toutes les applis
        [DataMember] public bool MouseHighlight = true;     // cadre jaune autour du texte lu sous la souris
        [DataMember] public int MouseDelayMs = 500;         // temps d'arrêt de la souris avant lecture
        [DataMember] public bool KeepInTray = true;         // la croix réduit Lisys près de l'horloge
        [DataMember] public bool TrayTipShown;
        [DataMember] public bool StartWithWindows;
        [DataMember] public string LastUrl = "";
        [DataMember] public string LastFolder = "";

        public static string Folder
        {
            get
            {
                string d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Lisys");
                Directory.CreateDirectory(d);
                return d;
            }
        }

        static string FilePath => Path.Combine(Folder, "reglages.json");

        static Settings current;

        public static Settings Current
        {
            get
            {
                if (current == null) current = Load();
                return current;
            }
        }

        static Settings Load()
        {
            try
            {
                if (File.Exists(FilePath))
                {
                    using (var fs = File.OpenRead(FilePath))
                    {
                        var s = (Settings)new DataContractJsonSerializer(typeof(Settings)).ReadObject(fs);
                        if (s != null)
                        {
                            if (s.Voice == null) s.Voice = "";
                            if (s.LastUrl == null) s.LastUrl = "";
                            if (s.LastFolder == null) s.LastFolder = "";
                            if (s.Rate <= 0) s.Rate = 1.0;
                            if (s.TextSize < 10) s.TextSize = 22f;
                            if (s.CaptionSize < 16) s.CaptionSize = 34f;
                            if (s.MouseDelayMs < 150) s.MouseDelayMs = 500;
                            return s;
                        }
                    }
                }
            }
            catch
            {
                // Fichier abîmé : on repart des réglages par défaut.
            }
            return new Settings();
        }

        public void Save()
        {
            try
            {
                string tmp = FilePath + ".tmp";
                using (var fs = File.Create(tmp))
                using (var w = JsonReaderWriterFactory.CreateJsonWriter(fs, Encoding.UTF8, true, true))
                {
                    new DataContractJsonSerializer(typeof(Settings)).WriteObject(w, this);
                }
                if (File.Exists(FilePath)) File.Delete(FilePath);
                File.Move(tmp, FilePath);
            }
            catch
            {
            }
        }

        public static string ThemeName(int t)
        {
            switch (t)
            {
                case ThemeSombre: return "Sombre";
                case ThemeContraste: return "Contraste élevé (jaune sur noir)";
                case ThemeSepia: return "Sépia";
                default: return "Clair";
            }
        }
    }
}
