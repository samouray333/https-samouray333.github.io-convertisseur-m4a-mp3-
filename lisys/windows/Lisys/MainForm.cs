using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

namespace Lisys
{
    /// <summary>Fenêtre principale : accueil (ouvrir, reprendre) et écran de lecture.</summary>
    public sealed partial class MainForm : Form
    {
        // Raccourcis valables dans toutes les applis.
        const int HkSelection = 1, HkMouse = 2, HkRegion = 3, HkPause = 4, HkClipboard = 5;

        readonly ReaderEngine engine = new ReaderEngine();
        readonly int openMessage = Native.RegisterWindowMessage("EchoMatras.Lisys.Ouvrir");
        Palette pal;

        // Accueil
        Panel home;
        ListBox recents;
        Label emptyHint;
        BigButton mouseButton;

        // Lecture
        Panel reader;
        RichTextBox rtb;
        SentenceView big;
        Label titleLabel, progressLabel, speedLabel;
        TrackBar position, speed;
        ComboBox voices;
        BigButton playButton;
        List<int> paraStart = new List<int>();
        int hlStart = -1, hlLen, wStart = -1, wLen;
        long userScrollAt;
        bool seekingBar;

        // Outils d'écran
        NotifyIcon tray;
        CaptionForm caption;
        HighlightForm highlight;
        readonly System.Windows.Forms.Timer mouseTimer = new System.Windows.Forms.Timer { Interval = 100 };
        bool mouseMode;
        Point lastMouse;
        long mouseStillSince;
        Point lastReadPoint = new Point(-9999, -9999);
        string lastMouseText;
        bool mouseBusy;
        bool exitRequested;
        readonly bool startHidden;

        public MainForm(string[] args)
        {
            startHidden = args.Contains("--tray");
            Text = "Lisys";
            Icon = LoadIcon();
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 12f);
            KeyPreview = true;
            AllowDrop = true;
            AutoScaleMode = AutoScaleMode.None;
            Size = new Size((int)(1080 * Dpi.Factor), (int)(760 * Dpi.Factor));
            MinimumSize = new Size((int)(760 * Dpi.Factor), (int)(560 * Dpi.Factor));

            BuildTray();
            BuildUi();
            engine.PositionChanged += OnPosition;
            engine.WordChanged += OnWord;
            engine.StateChanged += OnState;
            engine.DocumentChanged += OnDocumentChanged;
            engine.Finished += () => { HideCaptionSoon(); };
            mouseTimer.Tick += MouseTick;

            DragEnter += (s, e) => e.Effect = e.Data.GetDataPresent(DataFormats.FileDrop) || e.Data.GetDataPresent(DataFormats.Text) ? DragDropEffects.Copy : DragDropEffects.None;
            DragDrop += OnDrop;

            var files = args.Where(a => !a.StartsWith("--") && File.Exists(a)).ToList();
            if (files.Count > 0) Shown += (s, e) => OpenFile(files[0]);
            if (engine.Error != null) Shown += (s, e) => Warn(engine.Error);
        }

        static Icon LoadIcon()
        {
            try
            {
                using (var s = typeof(MainForm).Assembly.GetManifestResourceStream("Lisys.lisys.ico"))
                    return s != null ? new Icon(s) : SystemIcons.Application;
            }
            catch
            {
                return SystemIcons.Application;
            }
        }

        protected override void SetVisibleCore(bool value)
        {
            // Démarrage avec Windows : Lisys attend près de l'horloge, sans ouvrir la fenêtre.
            if (startHidden && !IsHandleCreated)
            {
                CreateHandle();
                value = false;
                OnLoadHidden();
            }
            base.SetVisibleCore(value);
        }

        void OnLoadHidden() => RegisterHotkeys();

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            if (!startHidden) RegisterHotkeys();
        }

        // ------------------------------------------------------------------ interface

        void BuildUi()
        {
            pal = Palette.Get(Settings.Current.Theme);
            SuspendLayout();
            Controls.Clear();
            BackColor = pal.Bg;
            ForeColor = pal.Text;
            BuildHome();
            BuildReader();
            Dpi.Scale(home);
            Dpi.Scale(reader);
            Controls.Add(reader);
            Controls.Add(home);
            reader.Visible = false;
            ResumeLayout();
            RefreshRecents();
        }

        Label MakeLabel(string text, float size, bool bold, Color color)
        {
            return new Label
            {
                Text = text,
                AutoSize = true,
                Font = new Font("Segoe UI", size, bold ? FontStyle.Bold : FontStyle.Regular),
                ForeColor = color,
                BackColor = Color.Transparent
            };
        }

        void BuildHome()
        {
            home = new Panel { Dock = DockStyle.Fill, BackColor = pal.Bg, Padding = new Padding(28, 20, 28, 16) };

            var head = new Panel { Dock = DockStyle.Top, Height = 92 };
            var title = MakeLabel("Lisys", 30, true, pal.Text);
            title.Location = new Point(0, 0);
            var sub = MakeLabel("Tes documents, pages web, photos et l'écran lus à voix haute", 13, false, pal.Muted);
            sub.Location = new Point(4, 56);
            var settings = new BigButton("Réglages", pal.Surface, pal.Text, 13) { Width = 150, Height = 52, TextAlign = ContentAlignment.MiddleCenter, Anchor = AnchorStyles.Top | AnchorStyles.Right, BorderColor = pal.Border };
            settings.Click += (s, e) => ShowSettings();
            head.Controls.Add(title);
            head.Controls.Add(sub);
            head.Controls.Add(settings);
            head.Resize += (s, e) => settings.Location = new Point(head.Width - settings.Width, 8);

            var grid = new TableLayoutPanel { Dock = DockStyle.Top, ColumnCount = 2, RowCount = 3, Height = 3 * 76, Padding = new Padding(0, 6, 0, 6) };
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            for (int i = 0; i < 3; i++) grid.RowStyles.Add(new RowStyle(SizeType.Absolute, 76));
            BigButton Add(string text, bool primary, EventHandler click, int col, int row)
            {
                var b = new BigButton(text, primary ? pal.Button : pal.Surface, primary ? pal.ButtonText : pal.Text) { Dock = DockStyle.Fill, Margin = new Padding(0, 0, col == 0 ? 10 : 0, 10) };
                if (!primary) b.BorderColor = pal.Border;
                b.Click += click;
                grid.Controls.Add(b, col, row);
                return b;
            }
            Add("Ouvrir un document      Ctrl+O", true, (s, e) => PickDocument(), 0, 0);
            Add("Lire une photo ou une image", true, (s, e) => PickImage(), 1, 0);
            Add("Lire une page web", true, (s, e) => AskUrl(), 0, 1);
            Add("Lire le texte copié      Ctrl+V", false, (s, e) => ReadClipboard(), 1, 1);
            mouseButton = Add("", false, (s, e) => ToggleMouseMode(), 0, 2);
            Add("Lire une zone de l'écran      Ctrl+Alt+O", false, (s, e) => ReadRegion(), 1, 2);
            UpdateMouseButton();

            var resume = MakeLabel("Reprendre la lecture", 15, true, pal.Text);
            var resumePanel = new Panel { Dock = DockStyle.Top, Height = 44 };
            resume.Location = new Point(0, 12);
            resumePanel.Controls.Add(resume);

            recents = new ListBox
            {
                Dock = DockStyle.Fill,
                DrawMode = DrawMode.OwnerDrawFixed,
                ItemHeight = 70,
                BorderStyle = BorderStyle.None,
                BackColor = pal.Bg,
                ForeColor = pal.Text,
                IntegralHeight = false,
                AccessibleName = "Documents récents"
            };
            recents.DrawItem += DrawRecent;
            recents.DoubleClick += (s, e) => OpenSelectedRecent(false);
            recents.KeyDown += (s, e) =>
            {
                if (e.KeyCode == Keys.Enter) { OpenSelectedRecent(false); e.Handled = true; }
                else if (e.KeyCode == Keys.Delete && recents.SelectedItem is Library.Entry en) { Library.Remove(en.Id); RefreshRecents(); }
            };
            recents.MouseUp += (s, e) =>
            {
                int i = recents.IndexFromPoint(e.Location);
                if (i < 0) return;
                recents.SelectedIndex = i;
                if (e.Button == MouseButtons.Left) { OpenSelectedRecent(false); return; }
                var en = (Library.Entry)recents.Items[i];
                var m = new ContextMenuStrip { Font = Font };
                m.Items.Add("Lire depuis le début", null, (a, b) => { Library.SavePosition(en.Id, 0, 0); OpenSelectedRecent(true); });
                m.Items.Add("Retirer de la liste", null, (a, b) => { Library.Remove(en.Id); RefreshRecents(); });
                m.Show(recents, e.Location);
            };

            emptyHint = MakeLabel("Aucun document pour l'instant. Glisse un fichier dans cette fenêtre, ou utilise les boutons ci-dessus.\n\n"
                                  + "Dans toutes les applis :\n"
                                  + "   Ctrl+Alt+L   lire le texte sélectionné (ou sous la souris)\n"
                                  + "   Ctrl+Alt+M   lecture sous la souris (on passe la souris, Lisys lit)\n"
                                  + "   Ctrl+Alt+O   lire une zone de l'écran (images, PDF scannés…)\n"
                                  + "   Ctrl+Alt+P   pause / reprise", 12.5f, false, pal.Muted);
            emptyHint.Dock = DockStyle.Fill;
            emptyHint.AutoSize = false;

            home.Controls.Add(recents);
            home.Controls.Add(emptyHint);
            home.Controls.Add(resumePanel);
            home.Controls.Add(grid);
            home.Controls.Add(head);
        }

        void DrawRecent(object sender, DrawItemEventArgs e)
        {
            if (e.Index < 0) return;
            var en = (Library.Entry)recents.Items[e.Index];
            bool sel = (e.State & DrawItemState.Selected) != 0;
            var r = new Rectangle(e.Bounds.X, e.Bounds.Y + 4, e.Bounds.Width - 2, e.Bounds.Height - 8);
            using (var b = new SolidBrush(sel ? pal.SentBg : pal.Surface))
            using (var path = BigButton.Rounded(r, 12))
            {
                e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                e.Graphics.FillPath(b, path);
            }
            using (var f1 = new Font("Segoe UI", 13, FontStyle.Bold))
            using (var f2 = new Font("Segoe UI", 11))
            {
                var c1 = sel ? pal.SentText : pal.Text;
                TextRenderer.DrawText(e.Graphics, en.Title, f1, new Rectangle(r.X + 14, r.Y + 6, r.Width - 28, 28), c1, TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
                string meta = en.Kind + "  ·  lu à " + en.Percent + " %  ·  " + en.OpenedDate.ToString("g");
                TextRenderer.DrawText(e.Graphics, meta, f2, new Rectangle(r.X + 14, r.Y + 34, r.Width - 28, 24), sel ? pal.SentText : pal.Muted, TextFormatFlags.EndEllipsis | TextFormatFlags.NoPrefix);
            }
        }

        void RefreshRecents()
        {
            if (recents == null) return;
            var list = Library.List();
            recents.BeginUpdate();
            recents.Items.Clear();
            foreach (var en in list) recents.Items.Add(en);
            recents.EndUpdate();
            emptyHint.Visible = list.Count == 0;
            recents.Visible = list.Count > 0;
        }

        void OpenSelectedRecent(bool fromStart)
        {
            if (!(recents.SelectedItem is Library.Entry en)) return;
            OpenReader(en.Id, fromStart);
        }

        void BuildReader()
        {
            reader = new Panel { Dock = DockStyle.Fill, BackColor = pal.Bg };

            // Barre du haut
            var top = new Panel { Dock = DockStyle.Top, Height = 66, BackColor = pal.Bar, Padding = new Padding(10, 8, 10, 8) };
            var back = new BigButton("← Accueil", pal.Surface, pal.BarText, 12) { Dock = DockStyle.Left, Width = 140, TextAlign = ContentAlignment.MiddleCenter };
            back.Click += (s, e) => ShowHome();
            var smaller = new BigButton("A−", pal.Surface, pal.BarText, 14) { Dock = DockStyle.Right, Width = 64, TextAlign = ContentAlignment.MiddleCenter, AccessibleName = "Texte plus petit" };
            smaller.Click += (s, e) => Zoom(-2);
            var bigger = new BigButton("A+", pal.Surface, pal.BarText, 14) { Dock = DockStyle.Right, Width = 64, TextAlign = ContentAlignment.MiddleCenter, AccessibleName = "Texte plus grand" };
            bigger.Click += (s, e) => Zoom(2);
            var loupe = new BigButton("Loupe", pal.Surface, pal.BarText, 12) { Dock = DockStyle.Right, Width = 100, TextAlign = ContentAlignment.MiddleCenter, AccessibleName = "Mode grand texte" };
            loupe.Click += (s, e) => ToggleBig();
            var more = new BigButton("Options", pal.Surface, pal.BarText, 12) { Dock = DockStyle.Right, Width = 110, TextAlign = ContentAlignment.MiddleCenter };
            more.Click += (s, e) => ReaderMenu(more);
            titleLabel = new Label { Dock = DockStyle.Fill, Font = new Font("Segoe UI", 14, FontStyle.Bold), ForeColor = pal.BarText, TextAlign = ContentAlignment.MiddleLeft, Padding = new Padding(14, 0, 0, 0), AutoEllipsis = true };
            foreach (var b in new[] { back, smaller, bigger, loupe, more }) { b.BackColor = pal.Bg; b.BorderColor = pal.Border; }
            top.Controls.Add(titleLabel);
            top.Controls.Add(Spacer(DockStyle.Right));
            top.Controls.Add(more);
            top.Controls.Add(Spacer(DockStyle.Right));
            top.Controls.Add(loupe);
            top.Controls.Add(Spacer(DockStyle.Right));
            top.Controls.Add(smaller);
            top.Controls.Add(Spacer(DockStyle.Right));
            top.Controls.Add(bigger);
            top.Controls.Add(back);

            // Texte
            rtb = new RichTextBox
            {
                Dock = DockStyle.Fill,
                ReadOnly = true,
                BorderStyle = BorderStyle.None,
                BackColor = pal.Bg,
                ForeColor = pal.Text,
                Font = new Font("Segoe UI", Settings.Current.TextSize),
                ScrollBars = RichTextBoxScrollBars.Vertical,
                HideSelection = true,
                DetectUrls = false,
                ShortcutsEnabled = true,
                Cursor = Cursors.Hand,
                AccessibleName = "Texte du document"
            };
            rtb.GotFocus += (s, e) => Native.HideCaret(rtb.Handle);
            rtb.MouseUp += OnTextClick;
            rtb.VScroll += (s, e) => { if (!programmaticScroll) userScrollAt = Environment.TickCount; };
            rtb.MouseWheel += (s, e) => userScrollAt = Environment.TickCount;
            var textHost = new Panel { Dock = DockStyle.Fill, Padding = new Padding(30, 16, 30, 10), BackColor = pal.Bg };
            textHost.Controls.Add(rtb);

            big = new SentenceView
            {
                Dock = DockStyle.Fill,
                BackColor = pal.Bg,
                ForeColor = pal.Text,
                WordBack = pal.WordBg,
                WordFore = pal.WordText,
                Font = new Font("Segoe UI", Math.Min(90, Settings.Current.TextSize * 2f), FontStyle.Bold),
                Visible = false
            };
            textHost.Controls.Add(big);

            // Commandes
            var bottom = new Panel { Dock = DockStyle.Bottom, Height = 196, BackColor = pal.Bar, Padding = new Padding(16, 8, 16, 10) };
            progressLabel = new Label { Dock = DockStyle.Top, Height = 26, ForeColor = pal.Muted, TextAlign = ContentAlignment.MiddleCenter, Font = new Font("Segoe UI", 11) };
            position = new TrackBar { Dock = DockStyle.Top, Height = 40, TickStyle = TickStyle.None, Minimum = 0, Maximum = 1, AccessibleName = "Position dans le document" };
            position.MouseDown += (s, e) => seekingBar = true;
            position.ValueChanged += (s, e) => { if (seekingBar) progressLabel.Text = "Aller au paragraphe " + (position.Value + 1) + " / " + engine.Paragraphs.Count; };
            position.MouseUp += (s, e) =>
            {
                seekingBar = false;
                userScrollAt = 0;
                engine.Seek(position.Value, 0);
            };

            var controls = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 74, FlowDirection = FlowDirection.LeftToRight, WrapContents = false };
            BigButton Ctl(string t, string name, int w, bool primary, Action a)
            {
                var b = new BigButton(t, primary ? pal.Button : pal.Bg, primary ? pal.ButtonText : pal.Text, primary ? 18 : 14)
                {
                    BorderColor = primary ? Color.Empty : pal.Border,
                    Width = w,
                    Height = 62,
                    TextAlign = ContentAlignment.MiddleCenter,
                    Margin = new Padding(6, 4, 6, 4),
                    AccessibleName = name
                };
                b.Click += (s, e) => { userScrollAt = 0; a(); };
                controls.Controls.Add(b);
                return b;
            }
            Ctl("⏮", "Paragraphe précédent   (Ctrl+Haut)", 76, false, engine.PreviousParagraph);
            Ctl("◀", "Phrase précédente   (Gauche)", 76, false, engine.Previous);
            playButton = Ctl("▶  Lire", "Lire ou mettre en pause   (Espace)", 180, true, engine.Toggle);
            Ctl("▶", "Phrase suivante   (Droite)", 76, false, engine.Next);
            Ctl("⏭", "Paragraphe suivant   (Ctrl+Bas)", 76, false, engine.NextParagraph);
            controls.Resize += (s, e) =>
            {
                int total = controls.Controls.Cast<Control>().Sum(c => c.Width + c.Margin.Horizontal);
                controls.Padding = new Padding(Math.Max(0, (controls.Width - total) / 2), 0, 0, 0);
            };

            var row = new FlowLayoutPanel { Dock = DockStyle.Top, Height = 46, WrapContents = false };
            speedLabel = new Label { Width = 150, Height = 40, TextAlign = ContentAlignment.MiddleRight, ForeColor = pal.BarText, Font = new Font("Segoe UI", 12, FontStyle.Bold) };
            speed = new TrackBar { Width = 260, Minimum = 5, Maximum = 30, TickStyle = TickStyle.None, Value = (int)Math.Round(Math.Max(0.5, Math.Min(3, Settings.Current.Rate)) * 10), AccessibleName = "Vitesse de lecture" };
            speed.ValueChanged += (s, e) => speedLabel.Text = "Vitesse " + (speed.Value / 10.0).ToString("0.0") + "×";
            speed.MouseUp += (s, e) => engine.SetRate(speed.Value / 10.0);
            speed.KeyUp += (s, e) => engine.SetRate(speed.Value / 10.0);
            speedLabel.Text = "Vitesse " + (speed.Value / 10.0).ToString("0.0") + "×";
            var voiceLabel = new Label { Text = "Voix", Width = 60, Height = 40, TextAlign = ContentAlignment.MiddleRight, ForeColor = pal.BarText, Font = new Font("Segoe UI", 12, FontStyle.Bold) };
            voices = new ComboBox { Width = 330, DropDownStyle = ComboBoxStyle.DropDownList, Font = new Font("Segoe UI", 12), AccessibleName = "Voix" };
            FillVoices();
            voices.SelectedIndexChanged += (s, e) =>
            {
                if (voices.SelectedItem is VoiceItem v && v.Name != engine.CurrentVoiceName)
                {
                    engine.SetVoice(v.Name);
                    if (!engine.Playing) engine.Preview(v.French ? "Bonjour, voici la voix choisie." : "Hello, this is the selected voice.");
                }
            };
            row.Controls.Add(speedLabel);
            row.Controls.Add(speed);
            row.Controls.Add(voiceLabel);
            row.Controls.Add(voices);
            row.Resize += (s, e) =>
            {
                int total = row.Controls.Cast<Control>().Sum(c => c.Width + c.Margin.Horizontal);
                row.Padding = new Padding(Math.Max(0, (row.Width - total) / 2), 0, 0, 0);
            };

            bottom.Controls.Add(row);
            bottom.Controls.Add(controls);
            bottom.Controls.Add(position);
            bottom.Controls.Add(progressLabel);

            reader.Controls.Add(textHost);
            reader.Controls.Add(bottom);
            reader.Controls.Add(top);
        }

        static Control Spacer(DockStyle d) => new Panel { Dock = d, Width = 8 };

        sealed class VoiceItem
        {
            public string Name, Label;
            public bool French;
            public override string ToString() => Label;
        }

        void FillVoices()
        {
            voices.Items.Clear();
            foreach (var v in engine.Voices())
            {
                voices.Items.Add(new VoiceItem
                {
                    Name = v.Name,
                    Label = ReaderEngine.VoiceLabel(v),
                    French = v.Culture != null && v.Culture.TwoLetterISOLanguageName == "fr"
                });
            }
            string cur = engine.CurrentVoiceName;
            for (int i = 0; i < voices.Items.Count; i++)
                if (((VoiceItem)voices.Items[i]).Name == cur) voices.SelectedIndex = i;
        }

        // ------------------------------------------------------------------ navigation

        void ShowHome()
        {
            reader.Visible = false;
            home.Visible = true;
            RefreshRecents();
            Text = "Lisys";
        }

        void OpenReader(string id, bool fromStart)
        {
            Library.Touch(id);
            engine.Load(id, true);
            if (fromStart) engine.Seek(0, 0);
            ShowReaderView();
            engine.Play();
        }

        void ShowReaderView()
        {
            home.Visible = false;
            reader.Visible = true;
            ApplyBig();
            BringToFrontSafe();
            rtb.Focus();
        }

        void BringToFrontSafe()
        {
            if (!Visible) Show();
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Activate();
        }

        // ------------------------------------------------------------------ affichage du texte

        void OnDocumentChanged()
        {
            titleLabel.Text = engine.Title;
            Text = engine.Title.Length > 0 ? engine.Title + " - Lisys" : "Lisys";
            RenderText();
            position.Maximum = Math.Max(1, engine.Paragraphs.Count - 1);
            position.Value = Math.Min(position.Maximum, Math.Max(0, engine.Para));
            HighlightSentence(engine.Para, engine.Sentence);
            UpdateProgress();
        }

        void RenderText()
        {
            hlStart = wStart = -1;
            paraStart = new List<int>();
            var sb = new System.Text.StringBuilder();
            foreach (var p in engine.Paragraphs)
            {
                paraStart.Add(sb.Length);
                sb.Append(p).Append("\n\n");
            }
            Native.SuspendDrawing(rtb);
            rtb.Font = new Font("Segoe UI", Settings.Current.TextSize);
            rtb.BackColor = pal.Bg;
            rtb.ForeColor = pal.Text;
            rtb.Text = sb.ToString();
            rtb.SelectAll();
            rtb.SelectionColor = pal.Text;
            rtb.SelectionBackColor = pal.Bg;
            rtb.Select(0, 0);
            Native.ResumeDrawing(rtb);
        }

        void HighlightSentence(int para, int sent)
        {
            if (para < 0 || para >= paraStart.Count) return;
            var ss = engine.Sentences(para);
            if (sent < 0 || sent >= ss.Count) return;
            int s = paraStart[para] + ss[sent][0], len = ss[sent][1] - ss[sent][0];
            Native.SuspendDrawing(rtb);
            if (hlStart >= 0 && hlStart + hlLen <= rtb.TextLength)
            {
                rtb.Select(hlStart, hlLen);
                rtb.SelectionBackColor = pal.Bg;
                rtb.SelectionColor = pal.Text;
            }
            if (s + len <= rtb.TextLength)
            {
                rtb.Select(s, len);
                rtb.SelectionBackColor = pal.SentBg;
                rtb.SelectionColor = pal.SentText;
            }
            hlStart = s;
            hlLen = len;
            wStart = -1;
            rtb.Select(s, 0);
            Native.ResumeDrawing(rtb);
            EnsureVisible(s);
        }

        void HighlightWord(int para, int start, int end)
        {
            if (!Settings.Current.FollowWord || para < 0 || para >= paraStart.Count) return;
            int s = paraStart[para] + start, len = Math.Max(0, end - start);
            if (s + len > rtb.TextLength) return;
            Native.SuspendDrawing(rtb);
            if (wStart >= 0 && wStart + wLen <= rtb.TextLength)
            {
                rtb.Select(wStart, wLen);
                rtb.SelectionBackColor = pal.SentBg;
                rtb.SelectionColor = pal.SentText;
            }
            rtb.Select(s, len);
            rtb.SelectionBackColor = pal.WordBg;
            rtb.SelectionColor = pal.WordText;
            wStart = s;
            wLen = len;
            rtb.Select(s, 0);
            Native.ResumeDrawing(rtb);
            EnsureVisible(s);
        }

        bool programmaticScroll;

        /// <summary>Garde la phrase lue visible, sauf si on vient de faire défiler soi-même.</summary>
        void EnsureVisible(int charIndex)
        {
            if (Environment.TickCount - userScrollAt < 5000 && userScrollAt != 0) return;
            var pt = rtb.GetPositionFromCharIndex(charIndex);
            int h = rtb.ClientSize.Height;
            if (pt.Y >= h / 10 && pt.Y <= h * 2 / 3) return;
            int line = Math.Max(1, rtb.Font.Height);
            int lines = (pt.Y - h / 5) / line;
            programmaticScroll = true;
            Native.SendMessage(rtb.Handle, 0x00B6 /* EM_LINESCROLL */, IntPtr.Zero, new IntPtr(lines));
            programmaticScroll = false;
        }

        void OnTextClick(object sender, MouseEventArgs e)
        {
            Native.HideCaret(rtb.Handle);
            if (e.Button != MouseButtons.Left || rtb.SelectionLength > 0) return;
            int idx = rtb.GetCharIndexFromPosition(e.Location);
            int p = 0;
            for (int i = 0; i < paraStart.Count; i++) if (paraStart[i] <= idx) p = i;
            if (paraStart.Count == 0) return;
            int off = idx - paraStart[p];
            var ss = engine.Sentences(p);
            int s = 0;
            for (int k = 0; k < ss.Count; k++) if (off >= ss[k][0]) s = k;
            userScrollAt = 0;
            engine.Seek(p, s);
            if (!engine.Playing) engine.Play();
        }

        void Zoom(int delta)
        {
            var st = Settings.Current;
            st.TextSize = Math.Max(12, Math.Min(60, st.TextSize + delta));
            st.Save();
            RenderText();
            HighlightSentence(engine.Para, engine.Sentence);
            big.Font = new Font("Segoe UI", Math.Min(90, st.TextSize * 2f), FontStyle.Bold);
            UpdateBig(-1, -1);
        }

        void ToggleBig()
        {
            Settings.Current.BigMode = !Settings.Current.BigMode;
            Settings.Current.Save();
            ApplyBig();
        }

        void ApplyBig()
        {
            bool on = Settings.Current.BigMode;
            big.Visible = on;
            rtb.Visible = !on;
            UpdateBig(-1, -1);
        }

        void UpdateBig(int ws, int we)
        {
            if (!big.Visible) return;
            var ss = engine.Sentences(engine.Para);
            if (engine.Sentence >= ss.Count) { big.SetText("", -1, -1); return; }
            var b = ss[engine.Sentence];
            string p = engine.Paragraphs[engine.Para];
            string sentence = p.Substring(b[0], b[1] - b[0]);
            int lead = sentence.Length - sentence.TrimStart().Length;
            big.SetText(sentence.Trim(), ws >= 0 ? ws - b[0] - lead : -1, we >= 0 ? we - b[0] - lead : -1);
        }

        void UpdateProgress()
        {
            int n = engine.Paragraphs.Count;
            if (n == 0 || seekingBar) return;
            int pct = n <= 1 ? 0 : (int)Math.Round(100.0 * engine.Para / (n - 1));
            progressLabel.Text = "Paragraphe " + (engine.Para + 1) + " / " + n + "   ·   " + pct + " %";
            position.Value = Math.Min(position.Maximum, Math.Max(0, engine.Para));
        }

        // ------------------------------------------------------------------ rappels du moteur

        void OnPosition(int para, int sent)
        {
            HighlightSentence(para, sent);
            UpdateProgress();
            UpdateBig(-1, -1);
            UpdateCaption(-1, -1);
        }

        void OnWord(int para, int start, int end)
        {
            HighlightWord(para, start, end);
            UpdateBig(start, end);
            UpdateCaption(start, end);
        }

        void OnState(bool playing)
        {
            playButton.Text = playing ? "❚❚  Pause" : "▶  Lire";
            playButton.AccessibleName = playing ? "Pause   (Espace)" : "Lire   (Espace)";
            if (!playing)
            {
                HideCaptionSoon();
                if (highlight != null && !mouseMode) highlight.Hide();
            }
            tray.Text = playing ? "Lisys : lecture en cours" : "Lisys";
        }

        // ------------------------------------------------------------------ bandeau

        bool CaptionWanted() => Settings.Current.Caption && engine.Playing && (mouseMode || !ContainsFocus || WindowState == FormWindowState.Minimized || !Visible);

        void UpdateCaption(int ws, int we)
        {
            if (!CaptionWanted())
            {
                if (caption != null && caption.Visible && !engine.Playing) HideCaptionSoon();
                else if (caption != null && caption.Visible && !Settings.Current.Caption) caption.Hide();
                return;
            }
            captionHide?.Stop();
            var ss = engine.Sentences(engine.Para);
            if (engine.Sentence >= ss.Count) return;
            var b = ss[engine.Sentence];
            string p = engine.Paragraphs[engine.Para];
            string sentence = p.Substring(b[0], b[1] - b[0]);
            int lead = sentence.Length - sentence.TrimStart().Length;
            if (caption == null || caption.IsDisposed) caption = new CaptionForm();
            caption.ShowSentence(sentence.Trim(), ws >= 0 ? ws - b[0] - lead : -1, we >= 0 ? we - b[0] - lead : -1);
        }

        System.Windows.Forms.Timer captionHide;

        void HideCaptionSoon()
        {
            if (caption == null || !caption.Visible) return;
            if (captionHide == null)
            {
                captionHide = new System.Windows.Forms.Timer { Interval = 1500 };
                captionHide.Tick += (s, e) => { captionHide.Stop(); if (!engine.Playing) caption?.Hide(); };
            }
            captionHide.Stop();
            captionHide.Start();
        }

        // ------------------------------------------------------------------ ouverture des documents

        void PickDocument()
        {
            using (var d = new OpenFileDialog
            {
                Title = "Ouvrir un document",
                Filter = "Documents lisibles|*.pdf;*.docx;*.odt;*.epub;*.rtf;*.txt;*.md;*.html;*.htm;*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.gif|"
                         + "PDF|*.pdf|Word|*.docx|OpenOffice|*.odt|Livres EPUB|*.epub|Images|*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.gif|Tous les fichiers|*.*",
                InitialDirectory = Directory.Exists(Settings.Current.LastFolder) ? Settings.Current.LastFolder : Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments)
            })
            {
                if (d.ShowDialog(this) != DialogResult.OK) return;
                Settings.Current.LastFolder = Path.GetDirectoryName(d.FileName);
                Settings.Current.Save();
                OpenFile(d.FileName);
            }
        }

        void PickImage()
        {
            using (var d = new OpenFileDialog
            {
                Title = "Lire une photo ou une image",
                Filter = "Images|*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.gif;*.webp;*.heic|PDF scanné|*.pdf|Tous les fichiers|*.*",
                InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyPictures)
            })
            {
                if (d.ShowDialog(this) != DialogResult.OK) return;
                if (Extractor.Ext(d.FileName) == "pdf") OcrPdf(d.FileName);
                else OcrImage(d.FileName);
            }
        }

        public void OpenFile(string path)
        {
            if (Extractor.IsImage(path)) { OcrImage(path); return; }
            RunJob("Ouverture du document…", Path.GetFullPath(path), p => Extractor.FromFile(path, p), path);
        }

        void AskUrl()
        {
            string clip = null;
            try { if (Clipboard.ContainsText()) clip = Clipboard.GetText(); } catch { }
            string url = clip != null ? FindUrl(clip) : null;
            string v = Prompt.Ask(this, "Lire une page web", "Adresse de la page (ou colle le lien) :", url ?? Settings.Current.LastUrl);
            if (string.IsNullOrWhiteSpace(v)) return;
            ImportUrl(v);
        }

        void ImportUrl(string url)
        {
            url = url.Trim();
            Settings.Current.LastUrl = url;
            Settings.Current.Save();
            RunJob("Chargement de la page…", WebExtractor.NormalizeUrl(url), p => WebExtractor.FromUrl(url, p), null);
        }

        static string FindUrl(string s)
        {
            var m = Regex.Match(s, @"https?://[^\s""'<>]+", RegexOptions.IgnoreCase);
            if (m.Success) return m.Value;
            m = Regex.Match(s.Trim(), @"^(www\.)?[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?$", RegexOptions.IgnoreCase);
            return m.Success ? m.Value : null;
        }

        void ReadClipboard()
        {
            string text = null;
            try
            {
                if (Clipboard.ContainsFileDropList())
                {
                    var f = Clipboard.GetFileDropList();
                    if (f.Count > 0) { OpenFile(f[0]); return; }
                }
                if (Clipboard.ContainsImage())
                {
                    using (var img = Clipboard.GetImage()) OcrBitmap(new Bitmap(img), "Image copiée");
                    return;
                }
                if (Clipboard.ContainsText()) text = Clipboard.GetText();
            }
            catch { }
            if (string.IsNullOrWhiteSpace(text))
            {
                text = Prompt.Ask(this, "Le presse-papiers est vide", "Colle ou écris ton texte :", "", true);
                if (string.IsNullOrWhiteSpace(text)) return;
            }
            string url = FindUrl(text);
            if (url != null && text.Trim().Length < url.Length + 40) ImportUrl(url);
            else ReadText("Texte copié", text, true);
        }

        /// <summary>Lit un texte tout de suite (sélection, presse-papiers…) ; il reste ensuite dans la liste.</summary>
        void ReadText(string fallbackTitle, string text, bool showReader)
        {
            string first = text.Trim().Split('\n')[0].Trim();
            string title = first.Length > 3 ? (first.Length > 60 ? first.Substring(0, 57) + "…" : first) : fallbackTitle;
            var r = Extractor.FromText(title, text);
            if (r.Paragraphs.Count == 0) return;
            var e = Library.Add(r, "texte:" + text.GetHashCode());
            Library.SavePosition(e.Id, 0, 0);
            engine.Load(e.Id, true);
            engine.Seek(0, 0);
            if (showReader) ShowReaderView();
            engine.Play();
            RefreshRecents();
        }

        void OnDrop(object sender, DragEventArgs e)
        {
            if (e.Data.GetData(DataFormats.FileDrop) is string[] files && files.Length > 0) { OpenFile(files[0]); return; }
            if (e.Data.GetData(DataFormats.Text) is string t && t.Trim().Length > 0)
            {
                string url = FindUrl(t);
                if (url != null && t.Trim().Length < url.Length + 40) ImportUrl(url);
                else ReadText("Texte déposé", t, true);
            }
        }

        // ------------------------------------------------------------------ tâches en arrière-plan

        BusyForm busy;

        void RunJob(string message, string source, Func<Action<string>, ExtractResult> job, string ocrPath)
        {
            busy = new BusyForm(message);
            busy.Show(this);
            Enabled = false;
            Task.Run(() =>
            {
                ExtractResult r = null;
                Exception error = null;
                try
                {
                    r = job(m => BeginInvoke((Action)(() => busy?.SetMessage(m))));
                    if (r == null || r.Paragraphs.Count == 0) error = new UserException("Aucun texte lisible n'a été trouvé.");
                }
                catch (Exception e) { error = e; }
                BeginInvoke((Action)(() =>
                {
                    Enabled = true;
                    busy?.Close();
                    busy = null;
                    if (error is NeedsOcrException && ocrPath != null)
                    {
                        if (MessageBox.Show(this, error.Message + "\n\nLisys peut reconnaître le texte des pages, comme pour une photo. Compte quelques secondes par page.\n\nLancer la reconnaissance de texte ?",
                                "Document scanné", MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes) OcrPdf(ocrPath);
                        return;
                    }
                    if (error != null)
                    {
                        Warn(error is UserException ? error.Message : "Impossible de lire ce document (" + error.Message + ").");
                        return;
                    }
                    var entry = Library.Add(r, source);
                    RefreshRecents();
                    OpenReader(entry.Id, false);
                }));
            });
        }

        void Warn(string message) => MessageBox.Show(this, message, "Lisys", MessageBoxButtons.OK, MessageBoxIcon.Information);

        // ------------------------------------------------------------------ reconnaissance de texte

        void OcrImage(string path)
        {
            RunOcr("Lecture du texte de l'image…", async (setMsg) => await Ocr.RecognizeFileAsync(path), Path.GetFileNameWithoutExtension(path), "photo:" + path + ":" + File.GetLastWriteTimeUtc(path).Ticks, true);
        }

        void OcrPdf(string path)
        {
            RunOcr("Lecture des pages…", async (setMsg) => await Ocr.RecognizePdfAsync(path, (i, n) => setMsg("Lecture de la page " + i + " / " + n + "…")),
                Path.GetFileNameWithoutExtension(path), "pdf-ocr:" + path, true);
        }

        void OcrBitmap(Bitmap bmp, string title, bool showReader = true)
        {
            RunOcr("Lecture du texte…", async (setMsg) => { try { return await Ocr.RecognizeBitmapAsync(bmp); } finally { bmp.Dispose(); } },
                title, "zone:" + DateTime.Now.Ticks, showReader);
        }

        async void RunOcr(string message, Func<Action<string>, Task<List<List<string>>>> job, string title, string source, bool showReader)
        {
            BusyForm b = null;
            if (showReader)
            {
                b = new BusyForm(message);
                b.Show(this);
            }
            try
            {
                var lines = await job(m => BeginInvoke((Action)(() => b?.SetMessage(m))));
                var paras = Extractor.OcrParagraphs(lines);
                b?.Close();
                if (Extractor.CountChars(paras) < 3)
                {
                    Notify("Je n'ai pas trouvé de texte. Pour une photo : nette, bien à plat, avec de la lumière.");
                    return;
                }
                var r = new ExtractResult { Title = title, Kind = "PHOTO", Paragraphs = paras };
                if (string.IsNullOrWhiteSpace(r.Title) || r.Title.StartsWith("Image") || r.Title.StartsWith("Zone"))
                    r.Title = paras[0].Length > 60 ? paras[0].Substring(0, 57) + "…" : paras[0];
                r = Extractor.Finish(r);
                var e = Library.Add(r, source);
                Library.SavePosition(e.Id, 0, 0);
                RefreshRecents();
                engine.Load(e.Id, true);
                engine.Seek(0, 0);
                if (showReader) ShowReaderView();
                engine.Play();
            }
            catch (Exception ex)
            {
                b?.Close();
                Notify(ex is UserException ? ex.Message : "Reconnaissance de texte impossible (" + ex.Message + ").");
            }
        }

        /// <summary>Message visible même quand la fenêtre est cachée.</summary>
        void Notify(string message)
        {
            if (Visible && WindowState != FormWindowState.Minimized && ContainsFocus) Warn(message);
            else
            {
                tray.ShowBalloonTip(6000, "Lisys", message, ToolTipIcon.Info);
                engine.Preview(message);
            }
        }

        void ReadRegion()
        {
            bool wasVisible = Visible && WindowState != FormWindowState.Minimized;
            if (wasVisible) WindowState = FormWindowState.Minimized;
            // Laisse le temps à la fenêtre de disparaître avant la capture.
            var t = new System.Windows.Forms.Timer { Interval = wasVisible ? 350 : 50 };
            t.Tick += (s, e) =>
            {
                t.Stop();
                t.Dispose();
                Rectangle bounds;
                var shot = ScreenTools.CaptureScreen(out bounds);
                using (var f = new RegionForm(shot, bounds))
                {
                    if (f.ShowDialog() != DialogResult.OK) { shot.Dispose(); return; }
                    var sel = Rectangle.Intersect(f.Selection, new Rectangle(Point.Empty, shot.Size));
                    if (sel.Width < 8 || sel.Height < 8) { shot.Dispose(); return; }
                    var part = shot.Clone(sel, shot.PixelFormat);
                    shot.Dispose();
                    // Petite zone : on l'agrandit, la reconnaissance est bien meilleure.
                    if (part.Width < 1200)
                    {
                        double k = Math.Min(3.0, 1200.0 / part.Width);
                        var scaled = new Bitmap(part, (int)(part.Width * k), (int)(part.Height * k));
                        part.Dispose();
                        part = scaled;
                    }
                    OcrBitmap(part, "Zone de l'écran", false);
                }
            };
            t.Start();
        }

        // ------------------------------------------------------------------ lecture de l'écran des autres applis

        void ReadSelection()
        {
            string text = ScreenTools.SelectedText();
            if (!string.IsNullOrWhiteSpace(text))
            {
                ReadText("Texte sélectionné", text, false);
                return;
            }
            // Rien de sélectionné : on lit le texte sous la souris.
            ReadUnderMouse(true);
        }

        void ToggleMouseMode()
        {
            mouseMode = !mouseMode;
            UpdateMouseButton();
            if (mouseMode)
            {
                lastMouseText = null;
                lastReadPoint = new Point(-9999, -9999);
                mouseTimer.Start();
                engine.Preview("Lecture sous la souris activée.");
            }
            else
            {
                mouseTimer.Stop();
                if (engine.DocId == null && engine.Playing) engine.Pause();
                highlight?.Hide();
                engine.Preview("Lecture sous la souris désactivée.");
            }
            UpdateTrayMenu();
        }

        void UpdateMouseButton()
        {
            if (mouseButton == null) return;
            mouseButton.Text = mouseMode ? "Lecture sous la souris : ACTIVÉE      Ctrl+Alt+M" : "Lecture sous la souris      Ctrl+Alt+M";
            mouseButton.BackColor = mouseMode ? pal.WordBg : pal.Surface;
            mouseButton.ForeColor = mouseMode ? pal.WordText : pal.Text;
        }

        void MouseTick(object sender, EventArgs e)
        {
            var p = Cursor.Position;
            long now = Environment.TickCount;
            if (p != lastMouse) { lastMouse = p; mouseStillSince = now; return; }
            if (now - mouseStillSince < Settings.Current.MouseDelayMs) return;
            if (Math.Abs(p.X - lastReadPoint.X) < 4 && Math.Abs(p.Y - lastReadPoint.Y) < 4) return;
            // Souris sur une fenêtre de Lisys : rien à faire.
            if (Bounds.Contains(p) && Visible && WindowState != FormWindowState.Minimized && ContainsFocus) return;
            lastReadPoint = p;
            ReadUnderMouse(false);
        }

        async void ReadUnderMouse(bool force)
        {
            if (mouseBusy) return;
            mouseBusy = true;
            var p = Cursor.Position;
            ScreenText st;
            try
            {
                st = await Task.Run(() => ScreenTools.TextAt(p));
                if (st != null && st.Self)
                {
                    // La souris est sur le cadre jaune ou le bandeau de Lisys : on les cache le temps de regarder dessous.
                    highlight?.Hide();
                    caption?.Hide();
                    await Task.Delay(60);
                    st = await Task.Run(() => ScreenTools.TextAt(p));
                    if (st != null && st.Self) st = null;
                }
            }
            finally { mouseBusy = false; }
            if (st == null || string.IsNullOrWhiteSpace(st.Text))
            {
                if (force) engine.Preview("Pas de texte sous la souris.");
                return;
            }
            string text = Regex.Replace(st.Text, @"\s+", " ").Trim();
            if (!force && text == lastMouseText && engine.Playing) return;
            lastMouseText = text;
            if (Settings.Current.MouseHighlight)
            {
                if (highlight == null || highlight.IsDisposed) highlight = new HighlightForm();
                highlight.SetRects(st.Rects);
            }
            var r = Extractor.FromText("Sous la souris", st.Text);
            if (r.Paragraphs.Count == 0) return;
            engine.LoadTransient("Sous la souris", r.Paragraphs);
            engine.Play();
        }

        // ------------------------------------------------------------------ raccourcis clavier globaux

        void RegisterHotkeys()
        {
            UnregisterHotkeys();
            if (!Settings.Current.Hotkeys) return;
            uint mods = Native.MOD_CONTROL | Native.MOD_ALT | Native.MOD_NOREPEAT;
            var failed = new List<string>();
            void Reg(int id, Keys k, string name) { if (!Native.RegisterHotKey(Handle, id, mods, (uint)k)) failed.Add(name); }
            Reg(HkSelection, Keys.L, "Ctrl+Alt+L");
            Reg(HkMouse, Keys.M, "Ctrl+Alt+M");
            Reg(HkRegion, Keys.O, "Ctrl+Alt+O");
            Reg(HkPause, Keys.P, "Ctrl+Alt+P");
            Reg(HkClipboard, Keys.C, "Ctrl+Alt+C");
            if (failed.Count > 0)
                tray.ShowBalloonTip(5000, "Lisys", "Raccourci déjà utilisé par une autre appli : " + string.Join(", ", failed), ToolTipIcon.Warning);
        }

        void UnregisterHotkeys()
        {
            if (!IsHandleCreated) return;
            for (int i = 1; i <= 5; i++) Native.UnregisterHotKey(Handle, i);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Native.WM_HOTKEY)
            {
                switch (m.WParam.ToInt32())
                {
                    case HkSelection: ReadSelection(); break;
                    case HkMouse: ToggleMouseMode(); break;
                    case HkRegion: ReadRegion(); break;
                    case HkPause: engine.Toggle(); break;
                    case HkClipboard: ReadClipboardQuiet(); break;
                }
                return;
            }
            if (m.Msg == openMessage && openMessage != 0)
            {
                // Une deuxième fois Lisys a été lancé (double-clic sur un fichier…) : on prend le relais.
                string f = Path.Combine(Settings.Folder, "ouvrir.txt");
                string path = null;
                try { if (File.Exists(f)) { path = File.ReadAllText(f).Trim(); File.Delete(f); } } catch { }
                BringToFrontSafe();
                if (!string.IsNullOrEmpty(path) && File.Exists(path)) OpenFile(path);
                return;
            }
            base.WndProc(ref m);
        }

        void ReadClipboardQuiet()
        {
            try
            {
                if (Clipboard.ContainsImage())
                {
                    using (var img = Clipboard.GetImage()) OcrBitmap(new Bitmap(img), "Image copiée", false);
                    return;
                }
                if (Clipboard.ContainsText()) ReadText("Texte copié", Clipboard.GetText(), false);
                else engine.Preview("Le presse-papiers est vide.");
            }
            catch { }
        }

        // ------------------------------------------------------------------ clavier dans la fenêtre

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (keyData == (Keys.Control | Keys.O)) { PickDocument(); return true; }
            if (keyData == (Keys.Control | Keys.V) && home.Visible) { ReadClipboard(); return true; }
            if (reader.Visible && !(ActiveControl is ComboBox) && !(ActiveControl is TextBox))
            {
                switch (keyData)
                {
                    case Keys.Space: engine.Toggle(); return true;
                    case Keys.Right: userScrollAt = 0; engine.Next(); return true;
                    case Keys.Left: userScrollAt = 0; engine.Previous(); return true;
                    case Keys.Control | Keys.Down: userScrollAt = 0; engine.NextParagraph(); return true;
                    case Keys.Control | Keys.Up: userScrollAt = 0; engine.PreviousParagraph(); return true;
                    case Keys.Control | Keys.Add: case Keys.Control | Keys.Oemplus: Zoom(2); return true;
                    case Keys.Control | Keys.Subtract: case Keys.Control | Keys.OemMinus: Zoom(-2); return true;
                    case Keys.Escape: ShowHome(); return true;
                    case Keys.Control | Keys.F: Search(); return true;
                }
            }
            return base.ProcessCmdKey(ref msg, keyData);
        }

        // ------------------------------------------------------------------ menus et réglages

        void ReaderMenu(Control anchor)
        {
            var m = new ContextMenuStrip { Font = new Font("Segoe UI", 12) };
            m.Items.Add("Rechercher dans le texte   (Ctrl+F)", null, (s, e) => Search());
            m.Items.Add("Créer un fichier audio (.m4a)", null, (s, e) => ExportAudio());
            m.Items.Add("Thème : " + Settings.ThemeName(Settings.Current.Theme), null, (s, e) => ChooseTheme());
            var follow = new ToolStripMenuItem("Surligner le mot lu") { Checked = Settings.Current.FollowWord };
            follow.Click += (s, e) => { Settings.Current.FollowWord = !Settings.Current.FollowWord; Settings.Current.Save(); HighlightSentence(engine.Para, engine.Sentence); };
            m.Items.Add(follow);
            var bigItem = new ToolStripMenuItem("Mode grand texte (loupe)") { Checked = Settings.Current.BigMode };
            bigItem.Click += (s, e) => ToggleBig();
            m.Items.Add(bigItem);
            m.Items.Add("Revenir au début", null, (s, e) => { userScrollAt = 0; engine.Seek(0, 0); });
            m.Items.Add("Copier tout le texte", null, (s, e) => { try { Clipboard.SetText(string.Join("\n\n", engine.Paragraphs)); } catch { } });
            m.Show(anchor, new Point(0, anchor.Height));
        }

        void Search()
        {
            string q = Prompt.Ask(this, "Rechercher", "Mot ou expression :", lastSearch);
            if (string.IsNullOrWhiteSpace(q)) return;
            q = q.Trim();
            if (!string.Equals(q, lastSearch, StringComparison.OrdinalIgnoreCase)) searchFrom = engine.Para + 1;
            lastSearch = q;
            var paras = engine.Paragraphs;
            for (int k = 0; k < paras.Count; k++)
            {
                int i = (searchFrom + k) % paras.Count;
                int at = paras[i].IndexOf(q, StringComparison.CurrentCultureIgnoreCase);
                if (at < 0) continue;
                searchFrom = i + 1;
                var ss = engine.Sentences(i);
                int s = 0;
                for (int j = 0; j < ss.Count; j++) if (at >= ss[j][0]) s = j;
                userScrollAt = 0;
                engine.Seek(i, s);
                return;
            }
            Warn("« " + q + " » introuvable.");
        }

        string lastSearch = "";
        int searchFrom;

        void ChooseTheme()
        {
            var names = Enumerable.Range(0, 4).Select(Settings.ThemeName).ToArray();
            int? t = Prompt.Choose(this, "Thème d'affichage", names, Settings.Current.Theme);
            if (t == null) return;
            Settings.Current.Theme = t.Value;
            Settings.Current.Save();
            bool inReader = reader.Visible;
            BuildUi();
            OnDocumentChanged();
            ApplyBig();
            OnState(engine.Playing);
            if (inReader) ShowReaderView();
        }

        CancellationTokenSource exportCancel;

        void ExportAudio()
        {
            if (engine.DocId == null) { Warn("Ce texte n'est pas enregistré dans la bibliothèque."); return; }
            if (exportCancel != null) { Warn("Un export est déjà en cours."); return; }
            int chars = engine.Paragraphs.Sum(p => p.Length);
            int minutes = Math.Max(1, (int)Math.Round(chars / (900 * Settings.Current.Rate)));
            if (MessageBox.Show(this, "Le document entier va être enregistré en fichier audio avec la voix et la vitesse actuelles (environ "
                                      + minutes + " min d'écoute).\n\nLe fichier sera dans Documents\\Lisys.", "Créer un fichier audio",
                    MessageBoxButtons.OKCancel, MessageBoxIcon.Information) != DialogResult.OK) return;
            string id = engine.DocId;
            exportCancel = new CancellationTokenSource();
            var token = exportCancel.Token;
            var b = new BusyForm("Création du fichier audio…", () => exportCancel?.Cancel());
            b.Show(this);
            Task.Run(() =>
            {
                string path = null;
                Exception error = null;
                try
                {
                    path = Exporter.Export(id, (i, n) => BeginInvoke((Action)(() => b.SetMessage("Création du fichier audio… " + (n == 0 ? 0 : 100 * i / n) + " %"))), token);
                }
                catch (Exception e) { error = e; }
                BeginInvoke((Action)(() =>
                {
                    b.Close();
                    exportCancel = null;
                    if (error is OperationCanceledException) return;
                    if (error != null) { Warn("Export impossible : " + error.Message); return; }
                    if (MessageBox.Show(this, "Fichier audio enregistré :\n" + path + "\n\nOuvrir le dossier ?", "Lisys",
                            MessageBoxButtons.YesNo, MessageBoxIcon.Information) == DialogResult.Yes)
                        Process.Start("explorer.exe", "/select,\"" + path + "\"");
                }));
            });
        }

        void ShowSettings()
        {
            using (var f = new SettingsForm(engine))
            {
                f.ShowDialog(this);
            }
            RegisterHotkeys();
            ApplyStartup();
            caption?.ApplySettings();
            FillVoices();
            speed.Value = (int)Math.Round(Math.Max(0.5, Math.Min(3, Settings.Current.Rate)) * 10);
            if (pal.Bg != Palette.Get(Settings.Current.Theme).Bg)
            {
                BuildUi();
                OnDocumentChanged();
                ApplyBig();
            }
        }

        public static void ApplyStartup()
        {
            try
            {
                using (var k = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Run"))
                {
                    if (Settings.Current.StartWithWindows) k.SetValue("Lisys", "\"" + Application.ExecutablePath + "\" --tray");
                    else if (k.GetValue("Lisys") != null) k.DeleteValue("Lisys");
                }
            }
            catch { }
        }

        // ------------------------------------------------------------------ icône près de l'horloge

        ToolStripMenuItem trayMouse;

        void BuildTray()
        {
            tray = new NotifyIcon { Icon = Icon, Text = "Lisys", Visible = true };
            var menu = new ContextMenuStrip { Font = new Font("Segoe UI", 11) };
            menu.Items.Add("Ouvrir Lisys", null, (s, e) => { BringToFrontSafe(); });
            menu.Items.Add("Lire le texte sélectionné   (Ctrl+Alt+L)", null, (s, e) => ReadSelection());
            trayMouse = new ToolStripMenuItem("Lecture sous la souris   (Ctrl+Alt+M)");
            trayMouse.Click += (s, e) => ToggleMouseMode();
            menu.Items.Add(trayMouse);
            menu.Items.Add("Lire une zone de l'écran   (Ctrl+Alt+O)", null, (s, e) => ReadRegion());
            menu.Items.Add("Pause / reprise   (Ctrl+Alt+P)", null, (s, e) => engine.Toggle());
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Quitter Lisys", null, (s, e) => { exitRequested = true; Close(); });
            tray.ContextMenuStrip = menu;
            tray.DoubleClick += (s, e) => BringToFrontSafe();
        }

        void UpdateTrayMenu()
        {
            if (trayMouse != null) trayMouse.Checked = mouseMode;
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (!exitRequested && e.CloseReason == CloseReason.UserClosing && Settings.Current.KeepInTray)
            {
                // La croix cache la fenêtre : les raccourcis restent disponibles.
                e.Cancel = true;
                Hide();
                if (!Settings.Current.TrayTipShown)
                {
                    Settings.Current.TrayTipShown = true;
                    Settings.Current.Save();
                    tray.ShowBalloonTip(8000, "Lisys reste disponible",
                        "Ctrl+Alt+L lit le texte sélectionné, Ctrl+Alt+M la lecture sous la souris. Clic droit sur l'icône près de l'horloge pour quitter.",
                        ToolTipIcon.Info);
                }
                return;
            }
            UnregisterHotkeys();
            mouseTimer.Stop();
            engine.Pause();
            engine.Dispose();
            tray.Visible = false;
            tray.Dispose();
            caption?.Close();
            highlight?.Close();
            base.OnFormClosing(e);
        }
    }
}
