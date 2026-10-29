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

    /** Bulle flottante affichée par le service d'accessibilité. */
    public static boolean bubble(Context c) { return sp(c).getBoolean("bubble", true); }
    public static void setBubble(Context c, boolean v) { sp(c).edit().putBoolean("bubble", v).apply(); }
    /** Taille de la bulle en dp. */
    public static int bubbleSize(Context c) { return sp(c).getInt("bubbleSize", 76); }
    public static void setBubbleSize(Context c, int v) { sp(c).edit().putInt("bubbleSize", v).apply(); }
    /** Couleur de la bulle : index dans Ui.BUBBLE_COLORS. */
    public static int bubbleColor(Context c) { return sp(c).getInt("bubbleColor", 0); }
    public static void setBubbleColor(Context c, int v) { sp(c).edit().putInt("bubbleColor", v).apply(); }
    /** Annonce vocale des actions de la bulle (« Mode doigt », « Arrêt »…). */
    public static boolean bubbleVoice(Context c) { return sp(c).getBoolean("bubbleVoice", true); }
    public static void setBubbleVoice(Context c, boolean v) { sp(c).edit().putBoolean("bubbleVoice", v).apply(); }
    /** Bandeau en très gros texte par-dessus les autres applis (désactivé par défaut). */
    public static boolean caption(Context c) { return sp(c).getBoolean("caption", false); }
    public static void setCaption(Context c, boolean v) { sp(c).edit().putBoolean("caption", v).apply(); }
    public static int captionSize(Context c) { return sp(c).getInt("captionSize", 34); }
    public static void setCaptionSize(Context c, int v) { sp(c).edit().putInt("captionSize", v).apply(); }
    public static int captionColors(Context c) { return sp(c).getInt("captionColors", 0); }
    public static void setCaptionColors(Context c, int v) { sp(c).edit().putInt("captionColors", v).apply(); }
    public static boolean captionTop(Context c) { return sp(c).getBoolean("captionTop", false); }
    public static void setCaptionTop(Context c, boolean v) { sp(c).edit().putBoolean("captionTop", v).apply(); }
    /** Double appui sur volume bas = lire l'écran ; appui long = lecture au doigt (désactivé par défaut). */
    public static boolean volumeKeys(Context c) { return sp(c).getBoolean("volumeKeys", false); }
    public static void setVolumeKeys(Context c, boolean v) { sp(c).edit().putBoolean("volumeKeys", v).apply(); }
    /** Annonce vocale des messages reçus (désactivée par défaut). */
    public static boolean announce(Context c) { return sp(c).getBoolean("announce", false); }
    public static void setAnnounce(Context c, boolean v) { sp(c).edit().putBoolean("announce", v).apply(); }
    public static boolean announceContent(Context c) { return sp(c).getBoolean("announceContent", true); }
    public static void setAnnounceContent(Context c, boolean v) { sp(c).edit().putBoolean("announceContent", v).apply(); }
    public static int bubbleX(Context c) { return sp(c).getInt("bubbleX", -1); }
    public static int bubbleY(Context c) { return sp(c).getInt("bubbleY", -1); }
    public static void setBubblePos(Context c, int x, int y) { sp(c).edit().putInt("bubbleX", x).putInt("bubbleY", y).apply(); }

    public static String lastUrl(Context c) { return sp(c).getString("lastUrl", ""); }
    public static void setLastUrl(Context c, String v) { sp(c).edit().putString("lastUrl", v).apply(); }
}
