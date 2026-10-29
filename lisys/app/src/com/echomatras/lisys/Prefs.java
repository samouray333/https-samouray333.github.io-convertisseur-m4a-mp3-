package com.echomatras.lisys;

import android.content.Context;
import android.content.SharedPreferences;

/** Réglages de l'appli (vitesse, voix, thème, taille du texte). */
public final class Prefs {
    private Prefs() {}

    public static final int THEME_CLAIR = 0;
    public static final int THEME_SOMBRE = 1;
    public static final int THEME_CONTRASTE = 2;
    public static final int THEME_SEPIA = 3;

    private static SharedPreferences sp(Context c) {
        return c.getSharedPreferences("reglages", Context.MODE_PRIVATE);
    }

    public static float rate(Context c) { return sp(c).getFloat("rate", 1.0f); }
    public static void setRate(Context c, float v) { sp(c).edit().putFloat("rate", v).apply(); }

    public static float pitch(Context c) { return sp(c).getFloat("pitch", 1.0f); }
    public static void setPitch(Context c, float v) { sp(c).edit().putFloat("pitch", v).apply(); }

    /** Nom de la voix choisie, vide = voix par défaut du téléphone. */
    public static String voice(Context c) { return sp(c).getString("voice", ""); }
    public static void setVoice(Context c, String v) { sp(c).edit().putString("voice", v).apply(); }

    public static int theme(Context c) { return sp(c).getInt("theme", THEME_CLAIR); }
    public static void setTheme(Context c, int v) { sp(c).edit().putInt("theme", v).apply(); }

    public static float textSize(Context c) { return sp(c).getFloat("textSize", 22f); }
    public static void setTextSize(Context c, float v) { sp(c).edit().putFloat("textSize", v).apply(); }

    public static boolean bigMode(Context c) { return sp(c).getBoolean("bigMode", false); }
    public static void setBigMode(Context c, boolean v) { sp(c).edit().putBoolean("bigMode", v).apply(); }

    public static boolean followWord(Context c) { return sp(c).getBoolean("followWord", true); }
    public static void setFollowWord(Context c, boolean v) { sp(c).edit().putBoolean("followWord", v).apply(); }

    public static String lastUrl(Context c) { return sp(c).getString("lastUrl", ""); }
    public static void setLastUrl(Context c, String v) { sp(c).edit().putString("lastUrl", v).apply(); }
}
