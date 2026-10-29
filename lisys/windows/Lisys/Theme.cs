using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace Lisys
{
    /// <summary>Couleurs des thèmes et composants d'interface (gros boutons, lisibles).</summary>
    public sealed class Palette
    {
        public Color Border;
        public Color Bg, Surface, Text, Muted, SentBg, SentText, WordBg, WordText, Bar, BarText, Button, ButtonText;
        public bool Dark;

        public static readonly Color Brand = Color.FromArgb(0x1E, 0x3A, 0x8A);

        public static Palette Get(int theme)
        {
            var p = new Palette();
            switch (theme)
            {
                case Settings.ThemeSombre:
                    p.Dark = true;
                    p.Bg = C(0x121417); p.Surface = C(0x23272E); p.Text = C(0xE8EAED); p.Muted = C(0x9AA0A6);
                    p.SentBg = C(0x27406B); p.SentText = C(0xFFFFFF); p.WordBg = C(0xF59E0B); p.WordText = C(0x000000);
                    p.Bar = C(0x1E2228); p.BarText = C(0xE8EAED); p.Button = C(0x3B82F6); p.ButtonText = Color.White;
                    break;
                case Settings.ThemeContraste:
                    p.Dark = true;
                    p.Bg = Color.Black; p.Surface = C(0x1A1A1A); p.Text = C(0xFFFF00); p.Muted = Color.White;
                    p.SentBg = C(0x0033CC); p.SentText = Color.White; p.WordBg = Color.White; p.WordText = Color.Black;
                    p.Bar = Color.Black; p.BarText = C(0xFFFF00); p.Button = C(0xFFFF00); p.ButtonText = Color.Black;
                    break;
                case Settings.ThemeSepia:
                    p.Bg = C(0xF4ECD8); p.Surface = C(0xEADFC4); p.Text = C(0x3B2F1E); p.Muted = C(0x7A6A50);
                    p.SentBg = C(0xF5D88A); p.SentText = C(0x3B2F1E); p.WordBg = C(0x8B5A00); p.WordText = Color.White;
                    p.Bar = C(0xEADFC4); p.BarText = C(0x3B2F1E); p.Button = C(0x8B5A00); p.ButtonText = Color.White;
                    break;
                default:
                    p.Bg = Color.White; p.Surface = C(0xF1F4F9); p.Text = C(0x111827); p.Muted = C(0x6B7280);
                    p.SentBg = C(0xFFE58A); p.SentText = C(0x111827); p.WordBg = Brand; p.WordText = Color.White;
                    p.Bar = C(0xF1F4F9); p.BarText = C(0x111827); p.Button = Brand; p.ButtonText = Color.White;
                    break;
            }
            p.Border = p.Dark ? (theme == Settings.ThemeContraste ? C(0xFFFF00) : C(0x5F6B7A)) : C(0x9AA5B8);
            return p;
        }

        static Color C(int rgb) => Color.FromArgb((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255);

        /// <summary>Couleurs du bandeau : nom, fond, texte, fond du mot lu, mot lu.</summary>
        public static readonly string[] CaptionNames = { "Jaune sur noir", "Blanc sur noir", "Noir sur blanc", "Noir sur jaune", "Blanc sur bleu" };

        public static readonly Color[][] CaptionColors =
        {
            new[] { Color.Black, C(0xFFFF00), Color.White, Color.Black },
            new[] { Color.Black, Color.White, C(0xFFFF00), Color.Black },
            new[] { Color.White, Color.Black, Brand, Color.White },
            new[] { C(0xFFEB3B), Color.Black, Color.Black, C(0xFFFF00) },
            new[] { Brand, Color.White, C(0xFFFF00), Color.Black },
        };
    }

    public static class Dpi
    {
        static float factor;

        /// <summary>Zoom de Windows (1 = 100 %, 1,5 = 150 %…).</summary>
        public static float Factor
        {
            get
            {
                if (factor > 0) return factor;
                try
                {
                    using (var g = Graphics.FromHwnd(IntPtr.Zero)) factor = Math.Max(1f, g.DpiX / 96f);
                }
                catch
                {
                    factor = 1f;
                }
                return factor;
            }
        }

        /// <summary>Agrandit positions et tailles écrites en pixels (les polices, en points, s'adaptent déjà).</summary>
        public static void Scale(Control c)
        {
            if (Math.Abs(Factor - 1f) > 0.01f) c.Scale(new SizeF(Factor, Factor));
        }
    }

    /// <summary>Gros bouton plat, arrondi, bien contrasté, utilisable au clavier.</summary>
    public sealed class BigButton : Button
    {
        public BigButton(string text, Color back, Color fore, float size = 15f)
        {
            Text = text;
            BackColor = back;
            ForeColor = fore;
            FlatStyle = FlatStyle.Flat;
            FlatAppearance.BorderSize = 0;
            FlatAppearance.MouseOverBackColor = ControlPaint.Light(back, 0.15f);
            Font = new Font("Segoe UI", size, FontStyle.Bold);
            TextAlign = ContentAlignment.MiddleLeft;
            Padding = new Padding(18, 0, 18, 0);
            Height = 64;
            Cursor = Cursors.Hand;
            UseVisualStyleBackColor = false;
            AccessibleName = text.Trim();
        }

        protected override void OnResize(EventArgs e)
        {
            base.OnResize(e);
            using (var path = Rounded(ClientRectangle, 14)) Region = new Region(path);
        }

        public static GraphicsPath Rounded(Rectangle r, int radius)
        {
            var p = new GraphicsPath();
            int d = radius * 2;
            if (r.Width <= d || r.Height <= d) { p.AddRectangle(r); return p; }
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        protected override void OnGotFocus(EventArgs e)
        {
            base.OnGotFocus(e);
            Invalidate();
        }

        /// <summary>Bordure bien visible (boutons clairs sur fond clair).</summary>
        public Color BorderColor = Color.Empty;

        /// <summary>Texte centré : on enlève la marge intérieure pour les petits boutons (A−, A+…).</summary>
        public new ContentAlignment TextAlign
        {
            get => base.TextAlign;
            set
            {
                base.TextAlign = value;
                if (value == ContentAlignment.MiddleCenter) Padding = new Padding(2);
            }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            if (!BorderColor.IsEmpty)
            {
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                using (var pen = new Pen(BorderColor, 2))
                using (var path = Rounded(new Rectangle(1, 1, Width - 3, Height - 3), 13))
                    e.Graphics.DrawPath(pen, path);
            }
            if (Focused)
            {
                // Contour épais quand le bouton a le focus clavier.
                using (var pen = new Pen(ForeColor, 3)) e.Graphics.DrawRectangle(pen, 3, 3, Width - 7, Height - 7);
            }
        }
    }
}
