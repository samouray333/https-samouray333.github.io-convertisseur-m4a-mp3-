import android.content.Context;
import android.content.ContextWrapper;
import com.qmtech.lisys.Extractor;
import com.qmtech.lisys.Sentences;
import com.qmtech.lisys.WebExtractor;
import java.io.File;

/** Tests sur PC des moteurs d'extraction de Lisys. Usage : TestExtract fichier... | url... */
public class TestExtract {
    public static void main(String[] args) throws Exception {
        final File cache = new File(System.getProperty("java.io.tmpdir"), "lisys-test");
        cache.mkdirs();
        Context c = new ContextWrapper(null) {
            @Override public Context getApplicationContext() { return this; }
            @Override public File getCacheDir() { return cache; }
        };
        for (String a : args) {
            System.out.println("==================== " + a);
            long t0 = System.currentTimeMillis();
            Extractor.Result r;
            try {
                if (a.startsWith("http")) r = WebExtractor.fromUrl(c, a, null);
                else {
                    String ext = a.substring(a.lastIndexOf('.') + 1);
                    r = Extractor.fromFile(c, new File(a), ext, null);
                    r = callFinish(r);
                }
            } catch (Exception e) {
                System.out.println("ERREUR : " + e);
                continue;
            }
            System.out.println("Titre : " + r.title + "   Type : " + r.kind + "   Paragraphes : " + r.paragraphs.size()
                    + "   (" + (System.currentTimeMillis() - t0) + " ms)");
            int max = Integer.getInteger("max", 12);
            for (int i = 0; i < Math.min(max, r.paragraphs.size()); i++) {
                String p = r.paragraphs.get(i);
                System.out.println("  [" + i + "] " + (p.length() > 220 ? p.substring(0, 220) + "…" : p));
                if (Boolean.getBoolean("sentences")) for (String s : Sentences.split(p)) System.out.println("       · " + s);
            }
        }
    }

    static Extractor.Result callFinish(Extractor.Result r) throws Exception {
        java.lang.reflect.Method m = Extractor.class.getDeclaredMethod("finish", Extractor.Result.class);
        m.setAccessible(true);
        return (Extractor.Result) m.invoke(null, r);
    }
}
