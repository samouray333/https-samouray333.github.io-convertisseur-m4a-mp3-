using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Automation;
using System.Windows.Automation.Text;
using System.Windows.Forms;

namespace Lisys
{
    /// <summary>Texte trouvé à l'écran, avec ses rectangles (pour le cadre jaune).</summary>
    public sealed class ScreenText
    {
        public string Text;
        public List<Rectangle> Rects = new List<Rectangle>();
        /// <summary>Le point est sur une fenêtre de Lisys (cadre jaune, bandeau).</summary>
        public bool Self;
    }

    /// <summary>
    /// Lecture de l'écran des autres applis avec UI Automation (l'accessibilité de Windows) :
    /// texte sous la souris, texte sélectionné.
    /// </summary>
    public static class ScreenTools
    {
        static readonly int MyPid = Process.GetCurrentProcess().Id;

        /// <summary>UI Automation peut bloquer si une appli ne répond pas : on limite le temps d'attente.</summary>
        static T WithTimeout<T>(Func<T> f, int ms) where T : class
        {
            T result = null;
            var t = new Thread(() =>
            {
                try { result = f(); } catch { result = null; }
            });
            t.IsBackground = true;
            t.SetApartmentState(ApartmentState.MTA);
            t.Start();
            return t.Join(ms) ? result : null;
        }

        /// <summary>Paragraphe (ou ligne) sous le point donné, en pixels écran.</summary>
        public static ScreenText TextAt(Point p) => WithTimeout(() => TextAtCore(p), 1500);

        static ScreenText TextAtCore(Point p)
        {
            var pt = new System.Windows.Point(p.X, p.Y);
            AutomationElement el = AutomationElement.FromPoint(pt);
            if (el == null) return null;
            if (el.Current.ProcessId == MyPid) return new ScreenText { Self = true };
            var walker = TreeWalker.ControlViewWalker;
            int depth = 0;
            for (var e = el; e != null && depth < 8; e = walker.GetParent(e), depth++)
            {
                if (!e.TryGetCurrentPattern(TextPattern.Pattern, out object tpo)) continue;
                try
                {
                    var tp = (TextPattern)tpo;
                    TextPatternRange range = tp.RangeFromPoint(pt);
                    range.ExpandToEnclosingUnit(TextUnit.Paragraph);
                    string text = range.GetText(6000);
                    if (string.IsNullOrWhiteSpace(text))
                    {
                        range = tp.RangeFromPoint(pt);
                        range.ExpandToEnclosingUnit(TextUnit.Line);
                        text = range.GetText(2000);
                    }
                    if (!string.IsNullOrWhiteSpace(text))
                    {
                        var st = new ScreenText { Text = text };
                        foreach (var r in range.GetBoundingRectangles())
                            st.Rects.Add(new Rectangle((int)r.X, (int)r.Y, (int)r.Width, (int)r.Height));
                        return st;
                    }
                }
                catch
                {
                    // Certaines applis donnent le motif texte mais refusent la position : on passe au nom.
                }
                break;
            }
            // Pas de texte détaillé : le nom de l'élément (bouton, lien, icône, cellule…).
            string name = el.Current.Name;
            if (string.IsNullOrWhiteSpace(name) && el.TryGetCurrentPattern(ValuePattern.Pattern, out object vp))
            {
                try { name = ((ValuePattern)vp).Current.Value; } catch { }
            }
            if (string.IsNullOrWhiteSpace(name)) return null;
            var b = el.Current.BoundingRectangle;
            var res = new ScreenText { Text = name };
            if (!b.IsEmpty && !double.IsInfinity(b.Width)) res.Rects.Add(new Rectangle((int)b.X, (int)b.Y, (int)b.Width, (int)b.Height));
            return res;
        }

        /// <summary>Texte sélectionné dans l'appli au premier plan.</summary>
        public static string SelectedText()
        {
            string viaUia = WithTimeout(() =>
            {
                var el = AutomationElement.FocusedElement;
                if (el == null || el.Current.ProcessId == MyPid) return null;
                if (!el.TryGetCurrentPattern(TextPattern.Pattern, out object tpo)) return null;
                var sel = ((TextPattern)tpo).GetSelection();
                string s = string.Join("\n", sel.Select(r => r.GetText(200000)));
                return string.IsNullOrWhiteSpace(s) ? null : s;
            }, 1500);
            if (!string.IsNullOrWhiteSpace(viaUia)) return viaUia;
            return CopySelection();
        }

        /// <summary>Copie la sélection avec Ctrl+C, puis remet le presse-papiers comme avant.</summary>
        static string CopySelection()
        {
            string backup = null;
            try { if (Clipboard.ContainsText()) backup = Clipboard.GetText(); } catch { }
            try { Clipboard.Clear(); } catch { }
            ReleaseModifiers();
            Native.SendCtrlC();
            string text = null;
            var sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < 600)
            {
                Application.DoEvents();
                Thread.Sleep(30);
                try
                {
                    if (Clipboard.ContainsText()) { text = Clipboard.GetText(); break; }
                }
                catch { }
            }
            try
            {
                if (backup != null) Clipboard.SetText(backup);
            }
            catch { }
            return string.IsNullOrWhiteSpace(text) ? null : text;
        }

        /// <summary>Le raccourci est encore enfoncé (Ctrl+Alt) : on relâche Alt et Maj pour que Ctrl+C passe bien.</summary>
        static void ReleaseModifiers()
        {
            var sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < 800 && (Native.IsDown(Keys.Menu) || Native.IsDown(Keys.ShiftKey) || Native.IsDown(Keys.LWin)))
            {
                Thread.Sleep(20);
            }
            Native.KeyUp(Keys.Menu);
            Native.KeyUp(Keys.ShiftKey);
        }

        /// <summary>Capture de tout l'écran (tous les moniteurs).</summary>
        public static Bitmap CaptureScreen(out Rectangle bounds)
        {
            bounds = SystemInformation.VirtualScreen;
            var bmp = new Bitmap(bounds.Width, bounds.Height);
            using (var g = Graphics.FromImage(bmp))
            {
                g.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size);
            }
            return bmp;
        }
    }

    static class Native
    {
        public const int WM_HOTKEY = 0x0312;
        public const uint MOD_ALT = 0x1, MOD_CONTROL = 0x2, MOD_SHIFT = 0x4, MOD_NOREPEAT = 0x4000;
        public const int WS_EX_TRANSPARENT = 0x20, WS_EX_LAYERED = 0x80000, WS_EX_TOOLWINDOW = 0x80, WS_EX_NOACTIVATE = 0x8000000, WS_EX_TOPMOST = 0x8;

        // Les appels à Windows sont protégés : si l'un d'eux manque (ancienne version, test sous Linux), Lisys continue.
        [DllImport("user32.dll", EntryPoint = "RegisterHotKey", SetLastError = true)]
        static extern bool RegisterHotKey_(IntPtr hWnd, int id, uint fsModifiers, uint vk);
        [DllImport("user32.dll", EntryPoint = "UnregisterHotKey")]
        static extern bool UnregisterHotKey_(IntPtr hWnd, int id);
        [DllImport("user32.dll", EntryPoint = "GetAsyncKeyState")]
        static extern short GetAsyncKeyState_(int vKey);
        [DllImport("user32.dll", EntryPoint = "HideCaret")]
        static extern bool HideCaret_(IntPtr hWnd);
        [DllImport("user32.dll", EntryPoint = "SendMessageW")]
        static extern IntPtr SendMessage_(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll", EntryPoint = "PostMessageW")]
        static extern bool PostMessage_(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll", EntryPoint = "RegisterWindowMessageW", CharSet = CharSet.Unicode)]
        static extern int RegisterWindowMessage_(string name);

        static T Safe<T>(Func<T> f, T fallback)
        {
            try { return f(); } catch (Exception) { return fallback; }
        }

        public static bool RegisterHotKey(IntPtr h, int id, uint mods, uint vk) => Safe(() => RegisterHotKey_(h, id, mods, vk), false);
        public static bool UnregisterHotKey(IntPtr h, int id) => Safe(() => UnregisterHotKey_(h, id), false);
        public static short GetAsyncKeyState(int vk) => Safe(() => GetAsyncKeyState_(vk), (short)0);
        public static bool HideCaret(IntPtr h) => Safe(() => HideCaret_(h), false);
        public static IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l) => Safe(() => SendMessage_(h, msg, w, l), IntPtr.Zero);
        public static bool PostMessage(IntPtr h, int msg, IntPtr w, IntPtr l) => Safe(() => PostMessage_(h, msg, w, l), false);
        public static int RegisterWindowMessage(string name) => Safe(() => RegisterWindowMessage_(name), 0);

        [DllImport("user32.dll")]
        static extern uint SendInput(uint n, INPUT[] inputs, int size);

        [StructLayout(LayoutKind.Sequential)]
        struct INPUT
        {
            public uint type;
            public KEYBDINPUT ki;
            public long pad1;   // l'union fait la taille de MOUSEINPUT
        }

        [StructLayout(LayoutKind.Sequential)]
        struct KEYBDINPUT
        {
            public ushort wVk;
            public ushort wScan;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        const uint KEYEVENTF_KEYUP = 2;

        public static bool IsDown(Keys k) => (GetAsyncKeyState((int)k) & 0x8000) != 0;

        static INPUT Key(Keys k, bool up) => new INPUT { type = 1, ki = new KEYBDINPUT { wVk = (ushort)k, dwFlags = up ? KEYEVENTF_KEYUP : 0 } };

        public static void KeyUp(Keys k)
        {
            if (!IsDown(k)) return;
            Safe(() => SendInput(1, new[] { Key(k, true) }, Marshal.SizeOf(typeof(INPUT))), 0u);
        }

        public static void SendCtrlC()
        {
            var inputs = new[] { Key(Keys.ControlKey, false), Key(Keys.C, false), Key(Keys.C, true), Key(Keys.ControlKey, true) };
            Safe(() => SendInput((uint)inputs.Length, inputs, Marshal.SizeOf(typeof(INPUT))), 0u);
        }

        public const int WM_SETREDRAW = 0x000B;

        public static void SuspendDrawing(Control c) => SendMessage(c.Handle, WM_SETREDRAW, IntPtr.Zero, IntPtr.Zero);

        public static void ResumeDrawing(Control c)
        {
            SendMessage(c.Handle, WM_SETREDRAW, new IntPtr(1), IntPtr.Zero);
            c.Invalidate();
        }
    }
}
