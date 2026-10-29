package android.util;

/** Version PC de android.util.Log pour les tests (n'affiche que les erreurs). */
public final class Log {
    public static final int VERBOSE = 2, DEBUG = 3, INFO = 4, WARN = 5, ERROR = 6, ASSERT = 7;
    private static int p(String lvl, String tag, String msg) {
        if (lvl.equals("E")) System.err.println(lvl + "/" + tag + ": " + msg);
        return 0;
    }
    public static int v(String t, String m) { return p("V", t, m); }
    public static int v(String t, String m, Throwable e) { return p("V", t, m); }
    public static int d(String t, String m) { return p("D", t, m); }
    public static int d(String t, String m, Throwable e) { return p("D", t, m); }
    public static int i(String t, String m) { return p("I", t, m); }
    public static int i(String t, String m, Throwable e) { return p("I", t, m); }
    public static int w(String t, String m) { return p("W", t, m); }
    public static int w(String t, String m, Throwable e) { return p("W", t, m); }
    public static int w(String t, Throwable e) { return p("W", t, String.valueOf(e)); }
    public static int e(String t, String m) { return p("E", t, m); }
    public static int e(String t, String m, Throwable e) { return p("E", t, m + " " + e); }
    public static boolean isLoggable(String t, int l) { return false; }
    public static String getStackTraceString(Throwable e) { return String.valueOf(e); }
}
