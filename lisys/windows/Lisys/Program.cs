using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Windows.Forms;

namespace Lisys
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            // Une seule copie de Lisys : la deuxième passe le fichier à ouvrir à la première.
            using (var mutex = new Mutex(true, "EchoMatras.Lisys", out bool first))
            {
                if (!first)
                {
                    string file = args.FirstOrDefault(a => !a.StartsWith("--") && File.Exists(a));
                    try
                    {
                        if (file != null) File.WriteAllText(Path.Combine(Settings.Folder, "ouvrir.txt"), Path.GetFullPath(file));
                    }
                    catch { }
                    int msg = Native.RegisterWindowMessage("EchoMatras.Lisys.Ouvrir");
                    Native.PostMessage(new IntPtr(0xFFFF) /* HWND_BROADCAST */, msg, IntPtr.Zero, IntPtr.Zero);
                    return;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.ThreadException += (s, e) => ShowError(e.Exception);
                AppDomain.CurrentDomain.UnhandledException += (s, e) => ShowError(e.ExceptionObject as Exception);
                Application.Run(new MainForm(args));
            }
        }

        static void ShowError(Exception e)
        {
            try
            {
                File.AppendAllText(Path.Combine(Settings.Folder, "erreurs.log"), DateTime.Now + " " + e + Environment.NewLine);
                MessageBox.Show("Un problème est survenu : " + e?.Message + "\n\nLe détail est dans " + Path.Combine(Settings.Folder, "erreurs.log"),
                    "Lisys", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
            catch { }
        }
    }
}
