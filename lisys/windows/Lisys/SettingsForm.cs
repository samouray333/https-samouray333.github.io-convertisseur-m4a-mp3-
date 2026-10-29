using System;
using System.Diagnostics;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;

namespace Lisys
{
    /// <summary>Réglages de Lisys, en une seule page, gros caractères.</summary>
    public sealed class SettingsForm : Form
    {
        static readonly int[] CaptionSizes = { 24, 34, 44, 56, 72 };
        static readonly string[] SizeNames = { "Petit", "Moyen", "Grand", "Très grand", "Géant" };
        static readonly int[] Delays = { 300, 500, 800, 1200 };

        public SettingsForm(ReaderEngine engine)
        {
            var s = Settings.Current;
            Text = "Réglages de Lisys";
            Font = new Font("Segoe UI", 12f);
            FormBorderStyle = FormBorderStyle.Sizable;
            StartPosition = FormStartPosition.CenterParent;
            MinimizeBox = false;
            ShowInTaskbar = false;
            ClientSize = new Size(760, 720);
            AutoScaleMode = AutoScaleMode.None;

            var flow = new FlowLayoutPanel
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.TopDown,
                WrapContents = false,
                AutoScroll = true,
                Padding = new Padding(22, 14, 22, 14)
            };
            Controls.Add(flow);

            Label Section(string t)
            {
                var l = new Label { Text = t, AutoSize = true, Font = new Font("Segoe UI", 15f, FontStyle.Bold), Margin = new Padding(0, 16, 0, 6) };
                flow.Controls.Add(l);
                return l;
            }
            ComboBox Combo(string label, string[] items, int selected, Action<int> changed)
            {
                var row = new FlowLayoutPanel { AutoSize = true, WrapContents = false, Margin = new Padding(0, 2, 0, 2) };
                row.Controls.Add(new Label { Text = label, Width = 260, Height = 36, TextAlign = ContentAlignment.MiddleLeft });
                var c = new ComboBox { DropDownStyle = ComboBoxStyle.DropDownList, Width = 400, AccessibleName = label };
                c.Items.AddRange(items);
                if (selected >= 0 && selected < items.Length) c.SelectedIndex = selected;
                c.SelectedIndexChanged += (a, b) => { if (c.SelectedIndex >= 0) changed(c.SelectedIndex); };
                row.Controls.Add(c);
                flow.Controls.Add(row);
                return c;
            }
            CheckBox Check(string label, bool value, Action<bool> changed)
            {
                var c = new CheckBox { Text = label, Checked = value, AutoSize = true, Margin = new Padding(0, 6, 0, 6) };
                c.CheckedChanged += (a, b) => changed(c.Checked);
                flow.Controls.Add(c);
                return c;
            }
            Button Link(string label, Action click)
            {
                var b = new Button { Text = label, AutoSize = true, Height = 44, Margin = new Padding(0, 4, 0, 4), Padding = new Padding(10, 4, 10, 4) };
                b.Click += (a, c) => click();
                flow.Controls.Add(b);
                return b;
            }

            Section("Lecture");
            Combo("Thème d'affichage", Enumerable.Range(0, 4).Select(Settings.ThemeName).ToArray(), s.Theme, i => s.Theme = i);
            var voices = engine.Voices();
            int vSel = voices.FindIndex(v => v.Name == engine.CurrentVoiceName);
            Combo("Voix", voices.Select(ReaderEngine.VoiceLabel).ToArray(), vSel, i => engine.SetVoice(voices[i].Name));
            var rates = new[] { 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 2.0, 2.5, 3.0 };
            int rSel = Array.FindIndex(rates, r => Math.Abs(r - s.Rate) < 0.05);
            Combo("Vitesse", rates.Select(r => r.ToString("0.0") + "×").ToArray(), rSel < 0 ? 2 : rSel, i => engine.SetRate(rates[i]));
            var sizes = new[] { 16, 18, 22, 26, 30, 36, 44, 52, 60 };
            int tSel = Array.FindIndex(sizes, z => Math.Abs(z - s.TextSize) < 1);
            Combo("Taille du texte", sizes.Select(z => z.ToString()).ToArray(), tSel < 0 ? 2 : tSel, i => s.TextSize = sizes[i]);
            Check("Surligner le mot prononcé", s.FollowWord, v => s.FollowWord = v);
            Link("Installer d'autres voix (Paramètres de Windows)…", () => OpenUri("ms-settings:speech"));

            Section("Bandeau en très gros texte");
            flow.Controls.Add(new Label { Text = "Quand Lisys lit pendant que tu es dans une autre appli, la phrase lue s'affiche en très gros.", AutoSize = true, MaximumSize = new Size(690, 0), ForeColor = SystemColors.GrayText });
            Check("Afficher le bandeau", s.Caption, v => s.Caption = v);
            int cs = Array.FindIndex(CaptionSizes, z => Math.Abs(z - s.CaptionSize) < 1);
            Combo("Taille du bandeau", SizeNames, cs < 0 ? 1 : cs, i => s.CaptionSize = CaptionSizes[i]);
            Combo("Couleurs du bandeau", Palette.CaptionNames, s.CaptionColors, i => s.CaptionColors = i);
            Combo("Position", new[] { "En bas de l'écran", "En haut de l'écran" }, s.CaptionTop ? 1 : 0, i => s.CaptionTop = i == 1);

            Section("Lecture sous la souris");
            int dSel = Array.IndexOf(Delays, s.MouseDelayMs);
            Combo("Temps avant de lire", new[] { "0,3 seconde", "0,5 seconde", "0,8 seconde", "1,2 seconde" }, dSel < 0 ? 1 : dSel, i => s.MouseDelayMs = Delays[i]);
            Check("Entourer en jaune le texte lu", s.MouseHighlight, v => s.MouseHighlight = v);

            Section("Général");
            Check("Raccourcis dans toutes les applis (Ctrl+Alt+L, M, O, P, C)", s.Hotkeys, v => s.Hotkeys = v);
            Check("Démarrer Lisys avec Windows (près de l'horloge)", s.StartWithWindows, v => s.StartWithWindows = v);
            Check("La croix garde Lisys près de l'horloge (raccourcis toujours actifs)", s.KeepInTray, v => s.KeepInTray = v);
            Link("Reconnaissance de texte : installer le français (Paramètres de Windows)…", () => OpenUri("ms-settings:regionlanguage"));
            Link("Vider la liste des documents", () =>
            {
                if (MessageBox.Show(this, "Retirer tous les documents de la liste ? (Tes fichiers d'origine ne sont pas supprimés.)", "Lisys",
                        MessageBoxButtons.OKCancel, MessageBoxIcon.Question) == DialogResult.OK) Library.Clear();
            });
            Link("À propos de Lisys", () => MessageBox.Show(this,
                "Lisys " + Application.ProductVersion + " · Echo Matras\n\n"
                + "Lecture à voix haute de documents (PDF, Word, OpenOffice, EPUB, RTF, HTML, texte), de pages web, de photos et de l'écran.\n\n"
                + "Tout est traité sur l'ordinateur avec la voix et la reconnaissance de texte de Windows. Rien n'est envoyé ailleurs (sauf le téléchargement des pages web demandées).\n\n"
                + "Bibliothèques : PdfPig (Apache 2.0), HtmlAgilityPack (MIT), NAudio (MIT).", "À propos", MessageBoxButtons.OK, MessageBoxIcon.Information));

            var close = new Button { Text = "Fermer", Dock = DockStyle.Bottom, Height = 52, Font = new Font("Segoe UI", 13f, FontStyle.Bold) };
            close.Click += (a, b) => Close();
            Controls.Add(close);
            AcceptButton = close;
            CancelButton = close;
            FormClosed += (a, b) => s.Save();
            Dpi.Scale(this);
        }

        static void OpenUri(string uri)
        {
            try { Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true }); } catch { }
        }
    }
}
