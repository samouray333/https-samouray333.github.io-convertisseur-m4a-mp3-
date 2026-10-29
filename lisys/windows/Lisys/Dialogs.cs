using System;
using System.Drawing;
using System.Windows.Forms;

namespace Lisys
{
    /// <summary>Petites fenêtres de saisie et de choix, en gros caractères.</summary>
    public static class Prompt
    {
        public static string Ask(IWin32Window owner, string title, string label, string value, bool multiline = false)
        {
            using (var f = new Form
            {
                Text = title,
                FormBorderStyle = FormBorderStyle.FixedDialog,
                StartPosition = FormStartPosition.CenterParent,
                MinimizeBox = false,
                MaximizeBox = false,
                ShowInTaskbar = false,
                Font = new Font("Segoe UI", 13f),
                ClientSize = new Size(640, multiline ? 360 : 190),
                AutoScaleMode = AutoScaleMode.None
            })
            {
                var l = new Label { Text = label, Location = new Point(20, 16), AutoSize = true };
                var box = new TextBox
                {
                    Text = value ?? "",
                    Location = new Point(20, 52),
                    Width = 600,
                    Multiline = multiline,
                    Height = multiline ? 220 : 36,
                    ScrollBars = multiline ? ScrollBars.Vertical : ScrollBars.None,
                    AcceptsReturn = multiline
                };
                var ok = new Button { Text = "OK", DialogResult = DialogResult.OK, Size = new Size(140, 48), Location = new Point(330, f.ClientSize.Height - 66) };
                var cancel = new Button { Text = "Annuler", DialogResult = DialogResult.Cancel, Size = new Size(140, 48), Location = new Point(480, f.ClientSize.Height - 66) };
                f.Controls.AddRange(new Control[] { l, box, ok, cancel });
                f.AcceptButton = multiline ? null : ok;
                f.CancelButton = cancel;
                f.Shown += (s, e) => { box.Focus(); box.SelectAll(); };
                Dpi.Scale(f);
                return f.ShowDialog(owner) == DialogResult.OK ? box.Text : null;
            }
        }

        public static int? Choose(IWin32Window owner, string title, string[] items, int selected)
        {
            using (var f = new Form
            {
                Text = title,
                FormBorderStyle = FormBorderStyle.FixedDialog,
                StartPosition = FormStartPosition.CenterParent,
                MinimizeBox = false,
                MaximizeBox = false,
                ShowInTaskbar = false,
                Font = new Font("Segoe UI", 13f),
                ClientSize = new Size(520, 90 + items.Length * 46),
                AutoScaleMode = AutoScaleMode.None
            })
            {
                var list = new ListBox { Location = new Point(20, 16), Size = new Size(480, items.Length * 46 + 4), ItemHeight = 44, DrawMode = DrawMode.OwnerDrawFixed, BorderStyle = BorderStyle.FixedSingle };
                list.Items.AddRange(items);
                list.DrawItem += (s, e) =>
                {
                    if (e.Index < 0) return;
                    e.DrawBackground();
                    TextRenderer.DrawText(e.Graphics, items[e.Index], f.Font, new Rectangle(e.Bounds.X + 10, e.Bounds.Y, e.Bounds.Width - 10, e.Bounds.Height),
                        (e.State & DrawItemState.Selected) != 0 ? SystemColors.HighlightText : SystemColors.WindowText, TextFormatFlags.VerticalCenter);
                };
                if (selected >= 0 && selected < items.Length) list.SelectedIndex = selected;
                var ok = new Button { Text = "OK", DialogResult = DialogResult.OK, Size = new Size(140, 48), Location = new Point(210, f.ClientSize.Height - 62) };
                var cancel = new Button { Text = "Annuler", DialogResult = DialogResult.Cancel, Size = new Size(140, 48), Location = new Point(360, f.ClientSize.Height - 62) };
                list.DoubleClick += (s, e) => { f.DialogResult = DialogResult.OK; f.Close(); };
                f.Controls.AddRange(new Control[] { list, ok, cancel });
                f.AcceptButton = ok;
                f.CancelButton = cancel;
                Dpi.Scale(f);
                return f.ShowDialog(owner) == DialogResult.OK && list.SelectedIndex >= 0 ? list.SelectedIndex : (int?)null;
            }
        }
    }

    /// <summary>Fenêtre « travail en cours » (ouverture d'un document, export…).</summary>
    public sealed class BusyForm : Form
    {
        readonly Label label;

        public BusyForm(string message, Action cancel = null)
        {
            FormBorderStyle = FormBorderStyle.FixedDialog;
            ControlBox = false;
            StartPosition = FormStartPosition.CenterParent;
            ShowInTaskbar = false;
            Text = "Lisys";
            Font = new Font("Segoe UI", 14f);
            ClientSize = new Size(560, cancel != null ? 170 : 120);
            AutoScaleMode = AutoScaleMode.None;
            var bar = new ProgressBar { Style = ProgressBarStyle.Marquee, Location = new Point(24, 70), Size = new Size(512, 22), MarqueeAnimationSpeed = 30 };
            label = new Label { Text = message, Location = new Point(24, 22), Size = new Size(512, 40) };
            Controls.Add(label);
            Controls.Add(bar);
            if (cancel != null)
            {
                var b = new Button { Text = "Annuler", Size = new Size(140, 46), Location = new Point(396, 108) };
                b.Click += (s, e) => { b.Enabled = false; label.Text = "Annulation…"; cancel(); };
                Controls.Add(b);
            }
            Dpi.Scale(this);
        }

        public void SetMessage(string m)
        {
            if (!IsDisposed) label.Text = m;
        }
    }
}
