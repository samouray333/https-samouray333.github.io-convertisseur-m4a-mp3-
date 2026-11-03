package com.qmtech.lisys;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Insets;
import android.os.Build;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Couleurs des thèmes et petits outils pour construire l'interface. */
final class Ui {
    private Ui() {}

    /** Politique de confidentialité (site GitHub Pages). */
    static final String PRIVACY_URL = "https://samouray333.github.io/https-samouray333.github.io-convertisseur-m4a-mp3-/lisys/confidentialite.html";

    static final int BRAND = 0xFF1E3A8A;      // bleu QMTech
    static final int BRAND_LIGHT = 0xFF3B82F6;
    static final int ACCENT = 0xFFF59E0B;     // ambre

    /** Couleurs de la bulle flottante : nom, fond, symbole, bordure (toujours bien contrastées). */
    static final String[] BUBBLE_COLOR_NAMES = {"Bleu", "Jaune", "Rouge", "Vert", "Orange", "Violet", "Noir", "Blanc"};
    static final int[][] BUBBLE_COLORS = {
            {0xFF1E3A8A, 0xFFFFFFFF, 0xFFFFFFFF},
            {0xFFFFD600, 0xFF000000, 0xFF000000},
            {0xFFD50000, 0xFFFFFFFF, 0xFFFFFFFF},
            {0xFF00701A, 0xFFFFFFFF, 0xFFFFFFFF},
            {0xFFFF6D00, 0xFF000000, 0xFF000000},
            {0xFF6A1B9A, 0xFFFFFFFF, 0xFFFFFFFF},
            {0xFF000000, 0xFFFFFF00, 0xFFFFFF00},
            {0xFFFFFFFF, 0xFF000000, 0xFF000000}};
    /** Couleurs du bandeau : nom, puis fond, texte, fond du mot lu, mot lu. */
    static final String[] CAPTION_COLOR_NAMES = {"Jaune sur noir", "Blanc sur noir", "Noir sur blanc", "Noir sur jaune", "Blanc sur bleu"};
    static final int[][] CAPTION_COLORS = {
            {0xF0000000, 0xFFFFFF00, 0xFFFFFFFF, 0xFF000000},
            {0xF0000000, 0xFFFFFFFF, 0xFFFFFF00, 0xFF000000},
            {0xF8FFFFFF, 0xFF000000, 0xFF1E3A8A, 0xFFFFFFFF},
            {0xF8FFEB3B, 0xFF000000, 0xFF000000, 0xFFFFFF00},
            {0xF01E3A8A, 0xFFFFFFFF, 0xFFFFFF00, 0xFF000000}};
    static final int[] CAPTION_SIZES = {26, 34, 44, 56, 72};

    static final int[] BUBBLE_SIZES = {56, 76, 96, 120, 150};
    static final String[] BUBBLE_SIZE_NAMES = {"Petit", "Moyen", "Grand", "Très grand", "Géant"};

    /** Couleurs d'un thème de lecture. */
    static final class Palette {
        int bg, surface, text, muted, paraBg, sentBg, wordBg, wordText, bar, barText, button, buttonText;
        boolean dark;
    }

    static Palette palette(Context c) {
        Palette p = new Palette();
        switch (Prefs.theme(c)) {
            case Prefs.THEME_SOMBRE:
                p.dark = true;
                p.bg = 0xFF121417; p.surface = 0xFF1E2228; p.text = 0xFFE8EAED; p.muted = 0xFF9AA0A6;
                p.paraBg = 0xFF1B2433; p.sentBg = 0xFF27406B; p.wordBg = 0xFFF59E0B; p.wordText = 0xFF000000;
                p.bar = 0xFF1E2228; p.barText = 0xFFE8EAED; p.button = 0xFF3B82F6; p.buttonText = 0xFFFFFFFF;
                break;
            case Prefs.THEME_CONTRASTE:
                p.dark = true;
                p.bg = 0xFF000000; p.surface = 0xFF000000; p.text = 0xFFFFFF00; p.muted = 0xFFFFFFFF;
                p.paraBg = 0xFF000000; p.sentBg = 0xFF0033CC; p.wordBg = 0xFFFFFFFF; p.wordText = 0xFF000000;
                p.bar = 0xFF000000; p.barText = 0xFFFFFF00; p.button = 0xFFFFFF00; p.buttonText = 0xFF000000;
                break;
            case Prefs.THEME_SEPIA:
                p.bg = 0xFFF4ECD8; p.surface = 0xFFEADFC4; p.text = 0xFF3B2F1E; p.muted = 0xFF7A6A50;
                p.paraBg = 0xFFEDE2C8; p.sentBg = 0xFFF5D88A; p.wordBg = 0xFF8B5A00; p.wordText = 0xFFFFFFFF;
                p.bar = 0xFFEADFC4; p.barText = 0xFF3B2F1E; p.button = 0xFF8B5A00; p.buttonText = 0xFFFFFFFF;
                break;
            default:
                p.bg = 0xFFFFFFFF; p.surface = 0xFFF3F5F9; p.text = 0xFF111827; p.muted = 0xFF6B7280;
                p.paraBg = 0xFFF1F5FF; p.sentBg = 0xFFFFE58A; p.wordBg = 0xFF1E3A8A; p.wordText = 0xFFFFFFFF;
                p.bar = 0xFFF3F5F9; p.barText = 0xFF111827; p.button = BRAND; p.buttonText = 0xFFFFFFFF;
        }
        return p;
    }

    static String themeName(int t) {
        switch (t) {
            case Prefs.THEME_SOMBRE: return "Sombre";
            case Prefs.THEME_CONTRASTE: return "Contraste élevé (jaune sur noir)";
            case Prefs.THEME_SEPIA: return "Sépia";
            default: return "Clair";
        }
    }

    static int dp(Context c, float v) {
        return Math.round(TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, c.getResources().getDisplayMetrics()));
    }

    /**
     * Affichage bord à bord (obligatoire depuis Android 15) : l'appli dessine sous les barres du système,
     * avec des icônes claires ou foncées selon le thème. Le contenu est décalé par {@link #setContent}.
     */
    static void systemBars(Activity a, Palette p) {
        Window w = a.getWindow();
        View decor = w.getDecorView();
        w.setStatusBarColor(Color.TRANSPARENT);
        w.setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= 30) {
            w.setDecorFitsSystemWindows(false);
            WindowInsetsController c = w.getInsetsController();
            if (c != null) {
                int mask = WindowInsetsController.APPEARANCE_LIGHT_STATUS_BARS | WindowInsetsController.APPEARANCE_LIGHT_NAVIGATION_BARS;
                c.setSystemBarsAppearance(p.dark ? 0 : mask, mask);
            }
        } else {
            int flags = View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION;
            if (!p.dark) flags |= View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR;
            decor.setSystemUiVisibility(flags);
        }
    }

    /** Affiche l'écran en laissant la place des barres du système et du clavier. */
    static void setContent(Activity a, View root) {
        a.setContentView(root);
        final int l = root.getPaddingLeft(), t = root.getPaddingTop(), r = root.getPaddingRight(), b = root.getPaddingBottom();
        root.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener() {
            @Override public WindowInsets onApplyWindowInsets(View v, WindowInsets in) {
                int il, it, ir, ib;
                if (Build.VERSION.SDK_INT >= 30) {
                    Insets bars = in.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                    Insets ime = in.getInsets(WindowInsets.Type.ime());
                    il = bars.left; it = bars.top; ir = bars.right; ib = Math.max(bars.bottom, ime.bottom);
                } else {
                    il = in.getSystemWindowInsetLeft(); it = in.getSystemWindowInsetTop();
                    ir = in.getSystemWindowInsetRight(); ib = in.getSystemWindowInsetBottom();
                }
                v.setPadding(l + il, t + it, r + ir, b + ib);
                return Build.VERSION.SDK_INT >= 30 ? WindowInsets.CONSUMED : in.consumeSystemWindowInsets();
            }
        });
        root.requestApplyInsets();
    }

    static GradientDrawable rounded(int color, float radiusPx) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(color);
        d.setCornerRadius(radiusPx);
        return d;
    }

    static void background(View v, int color, float radiusPx, int rippleColor) {
        v.setBackground(new RippleDrawable(ColorStateList.valueOf(rippleColor), rounded(color, radiusPx), null));
    }

    /** Gros bouton bien visible, avec description pour TalkBack. */
    static Button bigButton(Context c, String text, int bg, int fg) {
        Button b = new Button(c);
        b.setText(text);
        b.setAllCaps(false);
        b.setTextColor(fg);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 19);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
        b.setPadding(dp(c, 20), dp(c, 14), dp(c, 20), dp(c, 14));
        b.setMinHeight(dp(c, 64));
        b.setStateListAnimator(null);
        background(b, bg, dp(c, 16), 0x33FFFFFF);
        b.setContentDescription(spoken(text));
        return b;
    }

    /** Texte pour TalkBack : sans émojis ni symboles décoratifs. */
    static String spoken(String text) {
        return text.replaceAll("[\\x{1F000}-\\x{1FAFF}\\x{2600}-\\x{27BF}\\x{2190}-\\x{21FF}\\x{2B00}-\\x{2BFF}\\x{FE0F}\\x{200D}]", "")
                .replaceAll("\\s+", " ").trim();
    }

    /** Animations coupées dans les réglages du téléphone (Accessibilité > Supprimer les animations). */
    static boolean animationsOff(Context c) {
        try {
            return android.provider.Settings.Global.getFloat(c.getContentResolver(),
                    android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f;
        } catch (Exception e) {
            return false;
        }
    }

    /** Petite vibration de confirmation (si l'option est activée). */
    static void tick(View v) {
        if (Prefs.vibrate(v.getContext())) v.performHapticFeedback(android.view.HapticFeedbackConstants.VIRTUAL_KEY);
    }

    /** Fenêtres en gros texte, claires ou sombres selon le thème de Lisys. */
    static AlertDialog.Builder dialog(Context c) {
        return new BigDialog(c, palette(c).dark ? android.R.style.Theme_DeviceDefault_Dialog_Alert
                : android.R.style.Theme_DeviceDefault_Light_Dialog_Alert);
    }

    static final class BigDialog extends AlertDialog.Builder {
        private final Context ctx;

        BigDialog(Context c, int theme) {
            super(c, theme);
            ctx = getContext();
        }

        private ArrayAdapter<CharSequence> adapter(CharSequence[] items, int layout) {
            return new ArrayAdapter<CharSequence>(ctx, layout, items) {
                @Override public View getView(int pos, View convert, ViewGroup parent) {
                    View v = super.getView(pos, convert, parent);
                    if (v instanceof TextView) {
                        TextView t = (TextView) v;
                        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
                        t.setMinHeight(dp(ctx, 60));
                        t.setPadding(dp(ctx, 22), dp(ctx, 10), dp(ctx, 22), dp(ctx, 10));
                        t.setContentDescription(spoken(t.getText().toString()));
                    }
                    return v;
                }
            };
        }

        @Override public AlertDialog.Builder setItems(CharSequence[] items, DialogInterface.OnClickListener l) {
            return setAdapter(adapter(items, android.R.layout.simple_list_item_1), l);
        }

        @Override public AlertDialog.Builder setSingleChoiceItems(CharSequence[] items, int checked, DialogInterface.OnClickListener l) {
            return setSingleChoiceItems(adapter(items, android.R.layout.simple_list_item_single_choice), checked, l);
        }

        @Override public AlertDialog show() {
            AlertDialog d = super.show();
            TextView m = d.findViewById(android.R.id.message);
            if (m != null) m.setTextSize(TypedValue.COMPLEX_UNIT_SP, 19);
            for (int which : new int[]{AlertDialog.BUTTON_POSITIVE, AlertDialog.BUTTON_NEGATIVE, AlertDialog.BUTTON_NEUTRAL}) {
                Button b = d.getButton(which);
                if (b != null) { b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18); b.setMinHeight(dp(ctx, 56)); }
            }
            return d;
        }
    }

    /** Bouton rond des commandes de lecture. */
    static TextView roundButton(Context c, String glyph, String description, int bg, int fg, int sizeDp) {
        TextView t = new TextView(c);
        t.setText(glyph);
        t.setContentDescription(description);
        t.setGravity(Gravity.CENTER);
        t.setTextColor(fg);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeDp * 0.42f);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        GradientDrawable d = new GradientDrawable();
        d.setShape(GradientDrawable.OVAL);
        d.setColor(bg);
        t.setBackground(new RippleDrawable(ColorStateList.valueOf(0x44888888), d, null));
        t.setClickable(true);
        t.setFocusable(true);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(dp(c, sizeDp), dp(c, sizeDp));
        lp.setMargins(dp(c, 6), 0, dp(c, 6), 0);
        t.setLayoutParams(lp);
        return t;
    }

    static TextView label(Context c, String text, float sp, int color, boolean bold) {
        TextView t = new TextView(c);
        t.setText(text);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    static int withAlpha(int color, int alpha) {
        return Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color));
    }
}
