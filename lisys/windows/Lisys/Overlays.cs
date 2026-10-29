using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Linq;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace Lisys
{
    /// <summary>Affiche une phrase en très gros, avec le mot prononcé surligné (bandeau et mode loupe).</summary>
    public sealed class SentenceView : Control
    {
        string text = "";
        int wordStart = -1, wordEnd = -1;
        public Color WordBack = Color.White, WordFore = Color.Black;

        public SentenceView()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint | ControlStyles.ResizeRedraw, true);
            Padding = new Padding(18);
        }

        public void SetText(string t, int ws, int we)
        {
            text = t ?? "";
            wordStart = ws;
            wordEnd = we;
            AccessibleName = text;
            Invalidate();
        }

        struct Token { public string Word; public int Start; public int X; public int Line; public int Width; }

        List<Token> LayoutTokens(Graphics g, int width, out int lineHeight)
        {
            var tokens = new List<Token>();
            lineHeight = (int)(Font.Height * 1.12);
            int space = TextRenderer.MeasureText(g, " ", Font, Size.Empty, TextFormatFlags.NoPadding).Width;
            int x = 0, line = 0;
            foreach (Match m in Regex.Matches(text, @"\S+"))
            {
                int w = TextRenderer.MeasureText(g, m.Value, Font, Size.Empty, TextFormatFlags.NoPadding).Width;
                if (x > 0 && x + w > width) { x = 0; line++; }
                tokens.Add(new Token { Word = m.Value, Start = m.Index, X = x, Line = line, Width = w });
                x += w + space;
            }
            return tokens;
        }

        /// <summary>Hauteur nécessaire pour afficher le texte sur une largeur donnée (au plus maxLines lignes).</summary>
        public int NeededHeight(int width, int maxLines)
        {
            using (var g = CreateGraphics())
            {
                var t = LayoutTokens(g, width - Padding.Horizontal, out int lh);
                int lines = t.Count == 0 ? 1 : t.Max(k => k.Line) + 1;
                return Math.Min(lines, maxLines) * lh + Padding.Vertical;
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(BackColor);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            int width = Width - Padding.Horizontal;
            var tokens = LayoutTokens(g, width, out int lh);
            if (tokens.Count == 0) return;
            int maxLines = Math.Max(1, (Height - Padding.Vertical) / lh);
            int wordLine = 0;
            foreach (var t in tokens)
                if (wordStart >= 0 && t.Start <= wordStart && wordStart < t.Start + t.Word.Length + 1) wordLine = t.Line;
            int lastLine = tokens.Max(k => k.Line);
            int first = Math.Max(0, Math.Min(wordLine - maxLines / 3, lastLine - maxLines + 1));
            int y0 = Padding.Top;
            // Centré verticalement s'il y a de la place.
            int used = Math.Min(maxLines, lastLine + 1) * lh;
            if (used < Height - Padding.Vertical) y0 += (Height - Padding.Vertical - used) / 2;
            using (var hb = new SolidBrush(WordBack))
            {
                foreach (var t in tokens)
                {
                    if (t.Line < first || t.Line >= first + maxLines) continue;
                    int x = Padding.Left + t.X, y = y0 + (t.Line - first) * lh;
                    bool current = wordStart >= 0 && t.Start < wordEnd && wordStart < t.Start + t.Word.Length;
                    if (current)
                    {
                        var r = new Rectangle(x - 6, y - 2, t.Width + 12, lh);
                        using (var path = BigButton.Rounded(r, 8)) g.FillPath(hb, path);
                    }
                    TextRenderer.DrawText(g, t.Word, Font, new Point(x, y), current ? WordFore : ForeColor, TextFormatFlags.NoPadding);
                }
            }
        }
    }

    /// <summary>Bandeau en très gros texte, toujours au premier plan, que la souris traverse.</summary>
    public sealed class CaptionForm : Form
    {
        readonly SentenceView view = new SentenceView { Dock = DockStyle.Fill };

        public CaptionForm()
        {
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            Controls.Add(view);
            ApplySettings();
        }

        protected override bool ShowWithoutActivation => true;

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= Native.WS_EX_TOOLWINDOW | Native.WS_EX_NOACTIVATE | Native.WS_EX_TRANSPARENT | Native.WS_EX_LAYERED | Native.WS_EX_TOPMOST;
                return cp;
            }
        }

        public void ApplySettings()
        {
            var s = Settings.Current;
            var col = Palette.CaptionColors[Math.Max(0, Math.Min(s.CaptionColors, Palette.CaptionColors.Length - 1))];
            BackColor = view.BackColor = col[0];
            view.ForeColor = col[1];
            view.WordBack = col[2];
            view.WordFore = col[3];
            view.Font = new Font("Segoe UI", s.CaptionSize, FontStyle.Bold);
            Opacity = 0.96;
        }

        public void ShowSentence(string sentence, int ws, int we)
        {
            var screen = Screen.FromPoint(Cursor.Position).WorkingArea;
            int width = (int)(screen.Width * 0.94);
            view.SetText(sentence, ws, we);
            int h = Math.Max(view.Font.Height + 40, view.NeededHeight(width, 4));
            h = Math.Min(h, screen.Height * 2 / 5);
            int x = screen.Left + (screen.Width - width) / 2;
            int y = Settings.Current.CaptionTop ? screen.Top + 12 : screen.Bottom - h - 12;
            if (Bounds != new Rectangle(x, y, width, h)) Bounds = new Rectangle(x, y, width, h);
            if (!Visible) Show();
        }
    }

    /// <summary>Cadre jaune et noir autour du texte lu (lecture sous la souris).</summary>
    public sealed class HighlightForm : Form
    {
        List<Rectangle> rects = new List<Rectangle>();

        public HighlightForm()
        {
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.Magenta;
            TransparencyKey = Color.Magenta;
            Bounds = SystemInformation.VirtualScreen;
            DoubleBuffered = true;
        }

        protected override bool ShowWithoutActivation => true;

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= Native.WS_EX_TOOLWINDOW | Native.WS_EX_NOACTIVATE | Native.WS_EX_TRANSPARENT | Native.WS_EX_LAYERED | Native.WS_EX_TOPMOST;
                return cp;
            }
        }

        public void SetRects(IEnumerable<Rectangle> r)
        {
            var vs = SystemInformation.VirtualScreen;
            if (Bounds != vs) Bounds = vs;
            rects = r.Where(x => x.Width > 0 && x.Height > 0).ToList();
            if (rects.Count == 0) { Hide(); return; }
            if (!Visible) Show();
            Invalidate();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(Color.Magenta);
            var origin = Bounds.Location;
            using (var black = new Pen(Color.Black, 7))
            using (var yellow = new Pen(Color.FromArgb(0xFF, 0xD6, 0x00), 4))
            {
                foreach (var r0 in rects)
                {
                    var r = new Rectangle(r0.X - origin.X - 5, r0.Y - origin.Y - 4, r0.Width + 10, r0.Height + 8);
                    g.DrawRectangle(black, r);
                    g.DrawRectangle(yellow, r);
                }
            }
        }
    }

    /// <summary>Choix d'une zone de l'écran à lire (reconnaissance de texte) : on trace un rectangle.</summary>
    public sealed class RegionForm : Form
    {
        readonly Bitmap shot;
        Point start;
        Rectangle sel;
        bool dragging;
        public Rectangle Selection { get; private set; }

        public RegionForm(Bitmap screenshot, Rectangle bounds)
        {
            shot = screenshot;
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            Bounds = bounds;
            TopMost = true;
            ShowInTaskbar = false;
            DoubleBuffered = true;
            Cursor = Cursors.Cross;
            KeyPreview = true;
            KeyDown += (s, e) => { if (e.KeyCode == Keys.Escape) { DialogResult = DialogResult.Cancel; Close(); } };
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left) { DialogResult = DialogResult.Cancel; Close(); return; }
            start = e.Location;
            dragging = true;
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (!dragging) return;
            sel = new Rectangle(Math.Min(start.X, e.X), Math.Min(start.Y, e.Y), Math.Abs(e.X - start.X), Math.Abs(e.Y - start.Y));
            Invalidate();
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            if (!dragging) return;
            dragging = false;
            if (sel.Width < 12 || sel.Height < 12)
            {
                // Simple clic : toute la fenêtre / tout l'écran sous la souris.
                var scr = Screen.FromPoint(PointToScreen(e.Location)).Bounds;
                sel = new Rectangle(scr.X - Bounds.X, scr.Y - Bounds.Y, scr.Width, scr.Height);
            }
            Selection = sel;
            DialogResult = DialogResult.OK;
            Close();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.DrawImage(shot, 0, 0);
            using (var dim = new SolidBrush(Color.FromArgb(110, 0, 0, 0)))
            {
                var region = new Region(ClientRectangle);
                if (sel.Width > 0) region.Exclude(sel);
                g.FillRegion(dim, region);
            }
            if (sel.Width > 0)
            {
                using (var black = new Pen(Color.Black, 6)) g.DrawRectangle(black, sel);
                using (var yellow = new Pen(Color.FromArgb(0xFF, 0xD6, 0x00), 3)) g.DrawRectangle(yellow, sel);
            }
            string hint = "Trace un rectangle autour du texte à lire (ou clique pour tout l'écran). Échap pour annuler.";
            using (var f = new Font("Segoe UI", 20, FontStyle.Bold))
            {
                var size = TextRenderer.MeasureText(hint, f);
                var screen = Screen.PrimaryScreen.Bounds;
                var r = new Rectangle(screen.X - Bounds.X + (screen.Width - size.Width) / 2 - 16, screen.Y - Bounds.Y + 30, size.Width + 32, size.Height + 20);
                using (var bg = new SolidBrush(Color.FromArgb(0xFF, 0xD6, 0x00))) g.FillRectangle(bg, r);
                TextRenderer.DrawText(g, hint, f, r, Color.Black, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            }
        }
    }
}
