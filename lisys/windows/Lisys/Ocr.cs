using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage;
using Windows.Storage.Streams;

namespace Lisys
{
    /// <summary>
    /// Reconnaissance de texte avec le moteur intégré à Windows 10 et 11 (hors ligne) :
    /// photos, images, zones de l'écran et PDF scannés.
    /// </summary>
    public static class Ocr
    {
        static OcrEngine engine;

        public static OcrEngine Engine()
        {
            if (engine != null) return engine;
            try
            {
                var fr = new Language("fr-FR");
                if (OcrEngine.IsLanguageSupported(fr)) engine = OcrEngine.TryCreateFromLanguage(fr);
                if (engine == null) engine = OcrEngine.TryCreateFromUserProfileLanguages();
            }
            catch
            {
                engine = null;
            }
            if (engine == null)
                throw new UserException("La reconnaissance de texte de Windows n'est pas installée. Ouvre Paramètres > Heure et langue > "
                                        + "Langue, choisis Français, puis Options et installe « Reconnaissance optique de caractères ».");
            return engine;
        }

        /// <summary>Lit une image ; renvoie les paragraphes, chacun sous forme de lignes.</summary>
        public static async Task<List<List<string>>> RecognizeFileAsync(string path)
        {
            var file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(path));
            using (IRandomAccessStream stream = await file.OpenAsync(FileAccessMode.Read))
            {
                var decoder = await BitmapDecoder.CreateAsync(stream);
                return await RecognizeDecoderAsync(decoder, true);
            }
        }

        public static async Task<List<List<string>>> RecognizeBitmapAsync(System.Drawing.Bitmap bmp)
        {
            using (var ms = new MemoryStream())
            {
                bmp.Save(ms, System.Drawing.Imaging.ImageFormat.Png);
                ms.Position = 0;
                using (var ras = new InMemoryRandomAccessStream())
                {
                    var bytes = ms.ToArray();
                    using (var w = new DataWriter(ras))
                    {
                        w.WriteBytes(bytes);
                        await w.StoreAsync();
                        await w.FlushAsync();
                        w.DetachStream();
                    }
                    ras.Seek(0);
                    var decoder = await BitmapDecoder.CreateAsync(ras);
                    return await RecognizeDecoderAsync(decoder, false);
                }
            }
        }

        /// <summary>PDF scanné : chaque page est rendue en image puis lue.</summary>
        public static async Task<List<List<string>>> RecognizePdfAsync(string path, Action<int, int> progress)
        {
            var file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(path));
            var pdf = await Windows.Data.Pdf.PdfDocument.LoadFromFileAsync(file);
            var all = new List<List<string>>();
            for (uint i = 0; i < pdf.PageCount; i++)
            {
                progress?.Invoke((int)i + 1, (int)pdf.PageCount);
                using (var page = pdf.GetPage(i))
                using (var ras = new InMemoryRandomAccessStream())
                {
                    var opts = new Windows.Data.Pdf.PdfPageRenderOptions { DestinationWidth = 2000 };
                    await page.RenderToStreamAsync(ras, opts);
                    ras.Seek(0);
                    var decoder = await BitmapDecoder.CreateAsync(ras);
                    all.AddRange(await RecognizeDecoderAsync(decoder, false));
                }
            }
            return all;
        }

        static async Task<List<List<string>>> RecognizeDecoderAsync(BitmapDecoder decoder, bool tryRotations)
        {
            var eng = Engine();
            uint max = OcrEngine.MaxImageDimension;
            double scale = Math.Min(1.0, (double)max / Math.Max(decoder.OrientedPixelWidth, decoder.OrientedPixelHeight));
            List<List<string>> best = null;
            int bestChars = -1;
            // Photo prise avec le téléphone tourné : on essaie les autres sens si on trouve peu de texte.
            var rotations = tryRotations
                ? new[] { BitmapRotation.None, BitmapRotation.Clockwise90Degrees, BitmapRotation.Clockwise270Degrees, BitmapRotation.Clockwise180Degrees }
                : new[] { BitmapRotation.None };
            foreach (var rot in rotations)
            {
                var t = new BitmapTransform
                {
                    Rotation = rot,
                    ScaledWidth = (uint)Math.Max(1, decoder.OrientedPixelWidth * scale),
                    ScaledHeight = (uint)Math.Max(1, decoder.OrientedPixelHeight * scale),
                    InterpolationMode = BitmapInterpolationMode.Fant
                };
                using (var sb = await decoder.GetSoftwareBitmapAsync(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied, t,
                           ExifOrientationMode.RespectExifOrientation, ColorManagementMode.DoNotColorManage))
                {
                    var result = await eng.RecognizeAsync(sb);
                    var paras = Paragraphs(result);
                    int chars = paras.Sum(p => p.Sum(l => l.Count(char.IsLetterOrDigit)));
                    if (chars > bestChars) { best = paras; bestChars = chars; }
                    if (chars >= 40) break;
                }
            }
            return best ?? new List<List<string>>();
        }

        /// <summary>Regroupe les lignes reconnues en paragraphes (grand écart vertical = nouveau paragraphe).</summary>
        static List<List<string>> Paragraphs(OcrResult result)
        {
            var lines = new List<(string text, double top, double bottom, double left)>();
            foreach (var line in result.Lines)
            {
                if (line.Words.Count == 0) continue;
                double top = line.Words.Min(w => w.BoundingRect.Top);
                double bottom = line.Words.Max(w => w.BoundingRect.Bottom);
                double left = line.Words.Min(w => w.BoundingRect.Left);
                lines.Add((line.Text, top, bottom, left));
            }
            var paras = new List<List<string>>();
            if (lines.Count == 0) return paras;
            double medianHeight = lines.Select(l => l.bottom - l.top).OrderBy(h => h).ElementAt(lines.Count / 2);
            List<string> cur = null;
            (string text, double top, double bottom, double left) prev = default;
            foreach (var l in lines)
            {
                bool newPara = cur == null;
                if (!newPara)
                {
                    double gap = l.top - prev.bottom;
                    if (gap > medianHeight * 0.8 || gap < -medianHeight * 2) newPara = true; // grand blanc, ou autre colonne
                }
                if (newPara)
                {
                    cur = new List<string>();
                    paras.Add(cur);
                }
                cur.Add(l.text);
                prev = l;
            }
            return paras;
        }
    }
}
