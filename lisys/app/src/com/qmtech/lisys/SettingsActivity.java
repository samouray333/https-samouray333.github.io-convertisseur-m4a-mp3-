package com.qmtech.lisys;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;

import java.util.Locale;

/**
 * Tous les réglages sur un seul écran, en gros caractères, aux couleurs du thème.
 * Interrupteurs pour les options, appui pour passer au choix suivant (annoncé à voix haute).
 */
public class SettingsActivity extends Activity {

    private Ui.Palette pal;
    private LinearLayout list;
    private int themeShown = -1;

    interface Toggle { boolean get(); void set(boolean v); }
    interface Choice { int get(); void set(int i); }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        build();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (themeShown >= 0) build(); // retour des réglages d'Android : l'état du bouton flottant a pu changer
    }

    private void build() {
        themeShown = Prefs.theme(this);
        pal = Ui.palette(this);
        Ui.systemBars(this, pal);
        final Activity a = this;

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);
        LinearLayout head = new LinearLayout(this);
        head.setGravity(Gravity.CENTER_VERTICAL);
        int p = Ui.dp(this, 12);
        head.setPadding(p, p, p, p);
        head.setBackgroundColor(pal.bar);
        TextView back = Ui.roundButton(this, "←", Tr.t("Retour"), pal.surface, pal.text, 52);
        back.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { finish(); } });
        head.addView(back);
        TextView title = Ui.label(this, Tr.t("Réglages"), 26, pal.barText, true);
        title.setPadding(Ui.dp(this, 12), 0, 0, 0);
        head.addView(title);
        root.addView(head);

        ScrollView sv = new ScrollView(this);
        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        list.setPadding(Ui.dp(this, 16), Ui.dp(this, 4), Ui.dp(this, 16), Ui.dp(this, 32));
        sv.addView(list);
        root.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        // ---------------------------------------------------------------- affichage
        section(Tr.t("Affichage"));
        final String[] themes = {Ui.themeName(0), Ui.themeName(1), Ui.themeName(2), Ui.themeName(3)};
        choice(Tr.t("Thème"), themes, new Choice() {
            public int get() { return Prefs.theme(a); }
            public void set(int i) { Prefs.setTheme(a, i); build(); }
        });
        final int[] sizes = {18, 22, 26, 30, 36, 44, 52, 60};
        String[] sizeNames = new String[sizes.length];
        for (int i = 0; i < sizes.length; i++) sizeNames[i] = String.valueOf(sizes[i]);
        choice(Tr.t("Taille du texte de lecture"), sizeNames, new Choice() {
            public int get() { return nearest(sizes, Math.round(Prefs.textSize(a))); }
            public void set(int i) { Prefs.setTextSize(a, sizes[i]); }
        });
        toggle(Tr.t("Boutons de lecture géants"), new Toggle() {
            public boolean get() { return Prefs.bigControls(a); }
            public void set(boolean v) { Prefs.setBigControls(a, v); }
        });
        toggle(Tr.t("Surligner le mot prononcé"), new Toggle() {
            public boolean get() { return Prefs.followWord(a); }
            public void set(boolean v) { Prefs.setFollowWord(a, v); }
        });

        // ---------------------------------------------------------------- voix
        section(Tr.t("Voix"));
        final float[] rates = {0.6f, 0.8f, 1.0f, 1.2f, 1.4f, 1.6f, 2.0f, 2.5f, 3.0f};
        String[] rateNames = new String[rates.length];
        for (int i = 0; i < rates.length; i++) rateNames[i] = String.format(Locale.FRANCE, "%.1f×", rates[i]);
        choice(Tr.t("Vitesse de lecture"), rateNames, new Choice() {
            public int get() {
                int best = 2;
                for (int i = 0; i < rates.length; i++) if (Math.abs(rates[i] - Prefs.rate(a)) < Math.abs(rates[best] - Prefs.rate(a))) best = i;
                return best;
            }
            public void set(int i) { Prefs.setRate(a, rates[i]); }
        });
        action(Tr.t("Réglages de la synthèse vocale d'Android"), new Runnable() { public void run() { MainActivity.openTtsSettings(a); } });
        action(Tr.t("Installer d'autres voix"), new Runnable() { public void run() { MainActivity.installVoices(a); } });

        // ---------------------------------------------------------------- aide à l'utilisation
        section(Tr.t("Aide à l'utilisation"));
        toggle(Tr.t("Annonces vocales (« Pause », réglages…)"), new Toggle() {
            public boolean get() { return Prefs.voiceFeedback(a); }
            public void set(boolean v) { Prefs.setVoiceFeedback(a, v); }
        });
        toggle(Tr.t("Vibrations"), new Toggle() {
            public boolean get() { return Prefs.vibrate(a); }
            public void set(boolean v) { Prefs.setVibrate(a, v); }
        });
        toggle(Tr.t("Assistant : répondre à voix haute (oui, non, répète)"), new Toggle() {
            public boolean get() { return Prefs.voiceAnswers(a); }
            public void set(boolean v) { Prefs.setVoiceAnswers(a, v); }
        });
        action(Tr.t("Assistant de démarrage"), new Runnable() { public void run() { startActivity(new Intent(a, SetupActivity.class)); } });

        // ---------------------------------------------------------------- bouton flottant
        section(Tr.t("Bouton flottant (lire les autres applis)"));
        final boolean enabled = ScreenReaderService.isEnabled(this);
        action(enabled ? Tr.t("Bouton flottant : ✅ activé (désactiver)") : Tr.t("Bouton flottant : désactivé (activer)"), new Runnable() {
            public void run() {
                if (enabled || Prefs.a11yConsent(a)) MainActivity.openAccessibilitySettings(a);
                else MainActivity.showAccessibilityDisclosure(a, new Runnable() {
                    public void run() { MainActivity.openAccessibilitySettings(a); }
                });
            }
        });
        toggle(Tr.t("Afficher la bulle"), new Toggle() {
            public boolean get() { return Prefs.bubble(a); }
            public void set(boolean v) { Prefs.setBubble(a, v); }
        });
        choice(Tr.t("Taille de la bulle"), Ui.BUBBLE_SIZE_NAMES, new Choice() {
            public int get() { return nearest(Ui.BUBBLE_SIZES, Prefs.bubbleSize(a)); }
            public void set(int i) { Prefs.setBubbleSize(a, Ui.BUBBLE_SIZES[i]); }
        });
        choice(Tr.t("Couleur de la bulle"), Ui.BUBBLE_COLOR_NAMES, new Choice() {
            public int get() { return Prefs.bubbleColor(a); }
            public void set(int i) { Prefs.setBubbleColor(a, i); }
        });
        toggle(Tr.t("Lecture au doigt : continuer après la phrase touchée"), new Toggle() {
            public boolean get() { return Prefs.fingerContinue(a); }
            public void set(boolean v) { Prefs.setFingerContinue(a, v); }
        });
        toggle(Tr.t("Annonces vocales de la bulle"), new Toggle() {
            public boolean get() { return Prefs.bubbleVoice(a); }
            public void set(boolean v) { Prefs.setBubbleVoice(a, v); }
        });
        toggle(Tr.t("Bandeau en très gros texte"), new Toggle() {
            public boolean get() { return Prefs.caption(a); }
            public void set(boolean v) { Prefs.setCaption(a, v); }
        });
        choice(Tr.t("Taille du bandeau"), Ui.BUBBLE_SIZE_NAMES, new Choice() {
            public int get() { return nearest(Ui.CAPTION_SIZES, Prefs.captionSize(a)); }
            public void set(int i) { Prefs.setCaptionSize(a, Ui.CAPTION_SIZES[i]); }
        });
        choice(Tr.t("Couleurs du bandeau"), Ui.CAPTION_COLOR_NAMES, new Choice() {
            public int get() { return Prefs.captionColors(a); }
            public void set(int i) { Prefs.setCaptionColors(a, i); }
        });
        choice(Tr.t("Position du bandeau"), new String[]{Tr.t("En bas de l'écran"), Tr.t("En haut de l'écran")}, new Choice() {
            public int get() { return Prefs.captionTop(a) ? 1 : 0; }
            public void set(int i) { Prefs.setCaptionTop(a, i == 1); }
        });
        toggle(Tr.t("Boutons de volume (2 appuis sur volume bas : lire l'écran)"), new Toggle() {
            public boolean get() { return Prefs.volumeKeys(a); }
            public void set(boolean v) { Prefs.setVolumeKeys(a, v); }
        });
        toggle(Tr.t("Annoncer les messages reçus"), new Toggle() {
            public boolean get() { return Prefs.announce(a); }
            public void set(boolean v) { Prefs.setAnnounce(a, v); }
        });
        toggle(Tr.t("Lire aussi le texte des messages"), new Toggle() {
            public boolean get() { return Prefs.announceContent(a); }
            public void set(boolean v) { Prefs.setAnnounceContent(a, v); }
        });
        action(Tr.t("Comment marche le bouton flottant ?"), new Runnable() { public void run() { MainActivity.bubbleHowTo(a); } });
        action(Tr.t("Rapport de la dernière lecture (dépannage)"), new Runnable() { public void run() { MainActivity.showReport(a); } });

        // ---------------------------------------------------------------- divers
        section(Tr.t("Divers"));
        action(Tr.t("Vider la liste des documents"), new Runnable() { public void run() { MainActivity.confirmClear(a); } });
        action(Tr.t("Politique de confidentialité"), new Runnable() {
            public void run() {
                try { startActivity(new Intent(Intent.ACTION_VIEW, android.net.Uri.parse(Ui.PRIVACY_URL))); } catch (Exception ignored) {}
            }
        });
        action(Tr.t("À propos de Lisys"), new Runnable() { public void run() { MainActivity.about(a); } });

        Ui.setContent(this, root);
    }

    static int nearest(int[] values, int v) {
        int best = 0;
        for (int i = 0; i < values.length; i++) if (Math.abs(values[i] - v) < Math.abs(values[best] - v)) best = i;
        return best;
    }

    // ---------------------------------------------------------------- lignes

    private void section(String t) {
        TextView l = Ui.label(this, t, 21, pal.text, true);
        l.setPadding(Ui.dp(this, 4), Ui.dp(this, 26), 0, Ui.dp(this, 8));
        if (android.os.Build.VERSION.SDK_INT >= 28) l.setAccessibilityHeading(true);
        list.addView(l);
    }

    private LinearLayout row(String label, String value) {
        LinearLayout r = new LinearLayout(this);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setGravity(Gravity.CENTER_VERTICAL);
        int p = Ui.dp(this, 16);
        r.setPadding(p, Ui.dp(this, 12), p, Ui.dp(this, 12));
        r.setMinimumHeight(Ui.dp(this, 72));
        Ui.background(r, pal.surface, Ui.dp(this, 14), 0x33888888);
        r.setClickable(true);
        r.setFocusable(true);
        LinearLayout texts = new LinearLayout(this);
        texts.setOrientation(LinearLayout.VERTICAL);
        texts.addView(Ui.label(this, label, 19, pal.text, true));
        if (value != null) {
            TextView v = Ui.label(this, value, 17, pal.muted, false);
            v.setTag("value");
            texts.addView(v);
        }
        r.addView(texts, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 0, 0, Ui.dp(this, 10));
        list.addView(r, lp);
        return r;
    }

    private void toggle(final String label, final Toggle t) {
        final LinearLayout r = row(label, null);
        final Switch sw = new Switch(this);
        sw.setChecked(t.get());
        sw.setScaleX(1.4f);
        sw.setScaleY(1.4f);
        sw.setClickable(false);
        sw.setFocusable(false);
        sw.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        r.addView(sw);
        final Runnable describe = new Runnable() {
            public void run() { r.setContentDescription(Ui.spoken(label) + (sw.isChecked() ? Tr.t(", activé") : Tr.t(", désactivé"))); }
        };
        describe.run();
        r.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                boolean nv = !sw.isChecked();
                sw.setChecked(nv);
                t.set(nv);
                describe.run();
                Ui.tick(v);
                Speaker.say(SettingsActivity.this, Ui.spoken(label) + (nv ? Tr.t(" : activé") : Tr.t(" : désactivé")));
            }
        });
    }

    private void choice(final String label, final String[] names, final Choice c) {
        final LinearLayout r = row(label, names[Math.max(0, Math.min(c.get(), names.length - 1))] + Tr.t("   (appuie pour changer)"));
        final TextView value = (TextView) r.findViewWithTag("value");
        r.setContentDescription(label + ", " + names[Math.max(0, Math.min(c.get(), names.length - 1))] + Tr.t(". Appuie pour changer."));
        r.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                int next = (Math.max(0, c.get()) + 1) % names.length;
                c.set(next);
                if (isFinishing()) return;
                value.setText(names[next] + Tr.t("   (appuie pour changer)"));
                r.setContentDescription(label + ", " + names[next] + Tr.t(". Appuie pour changer."));
                Ui.tick(v);
                Speaker.say(SettingsActivity.this, label + " : " + Ui.spoken(names[next]));
            }
        });
        // Appui long : liste complète des choix.
        r.setOnLongClickListener(new View.OnLongClickListener() {
            @Override public boolean onLongClick(View v) {
                Ui.dialog(SettingsActivity.this).setTitle(label)
                        .setSingleChoiceItems(names, c.get(), new android.content.DialogInterface.OnClickListener() {
                            @Override public void onClick(android.content.DialogInterface d, int w) {
                                d.dismiss();
                                c.set(w);
                                if (!isFinishing()) build();
                            }
                        }).show();
                return true;
            }
        });
    }

    private void action(final String label, final Runnable run) {
        LinearLayout r = row(label, null);
        TextView arrow = Ui.label(this, "›", 30, pal.muted, true);
        arrow.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        r.addView(arrow);
        r.setContentDescription(Ui.spoken(label));
        r.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { Ui.tick(v); run.run(); }
        });
    }
}
