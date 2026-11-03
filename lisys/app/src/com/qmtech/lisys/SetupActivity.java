package com.qmtech.lisys;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * Assistant de démarrage, lu à voix haute : confort d'affichage, notifications,
 * puis activation guidée du bouton flottant (la partie la plus compliquée d'Android).
 */
public class SetupActivity extends Activity {

    private static final int STEP_WELCOME = 0, STEP_NOTIF = 1, STEP_BUBBLE = 2, STEP_DONE = 3;
    private int step = STEP_WELCOME;
    private boolean sentToSettings;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (state != null) step = state.getInt("step", STEP_WELCOME);
        show();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        out.putInt("step", step);
    }

    @Override
    protected void onResume() {
        super.onResume();
        // Retour des réglages d'Android : on vérifie tout seul si le bouton flottant est activé.
        if (step == STEP_BUBBLE && sentToSettings) {
            sentToSettings = false;
            if (ScreenReaderService.isEnabled(this)) { step = STEP_DONE; show(); }
            else Speaker.say(this, "Le bouton flottant n'est pas encore activé. Tu peux réessayer, ou passer cette étape.");
        }
    }

    private void next() {
        step++;
        if (step == STEP_NOTIF && (Build.VERSION.SDK_INT < 33
                || checkSelfPermission("android.permission.POST_NOTIFICATIONS") == PackageManager.PERMISSION_GRANTED)) step++;
        if (step == STEP_BUBBLE && ScreenReaderService.isEnabled(this)) step++;
        if (step > STEP_DONE) { finishSetup(); return; }
        show();
    }

    private void finishSetup() {
        Prefs.setSetupDone(this, true);
        finish();
    }

    private void show() {
        Ui.Palette pal = Ui.palette(this);
        Ui.systemBars(this, pal);
        String title, text;
        LinearLayout buttons = new LinearLayout(this);
        buttons.setOrientation(LinearLayout.VERTICAL);
        switch (step) {
            case STEP_WELCOME:
                title = "Bienvenue dans Lisys";
                text = "Lisys lit à voix haute tes documents, les pages web, le courrier en photo, et tout ce qui est "
                        + "affiché sur le téléphone.\n\nAvant de commencer, choisis un affichage confortable. "
                        + "Tu pourras tout changer plus tard dans les réglages.";
                addButton(buttons, pal, Prefs.theme(this) == Prefs.THEME_CONTRASTE ? "Affichage normal (noir sur blanc)"
                        : "Contraste élevé (jaune sur noir)", false, new Runnable() {
                    public void run() {
                        Prefs.setTheme(SetupActivity.this, Prefs.theme(SetupActivity.this) == Prefs.THEME_CONTRASTE
                                ? Prefs.THEME_CLAIR : Prefs.THEME_CONTRASTE);
                        show();
                    }
                });
                addButton(buttons, pal, Prefs.bigControls(this) ? "Boutons normaux" : "Boutons géants", false, new Runnable() {
                    public void run() { Prefs.setBigControls(SetupActivity.this, !Prefs.bigControls(SetupActivity.this)); show(); }
                });
                addButton(buttons, pal, "Continuer", true, new Runnable() { public void run() { next(); } });
                break;
            case STEP_NOTIF:
                title = "Notifications";
                text = "Lisys affiche les commandes de lecture (pause, phrase suivante) dans les notifications et sur "
                        + "l'écran verrouillé. Appuie sur « Autoriser », puis accepte dans la fenêtre d'Android.";
                addButton(buttons, pal, "Autoriser", true, new Runnable() {
                    public void run() { requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1); }
                });
                addButton(buttons, pal, "Passer", false, new Runnable() { public void run() { next(); } });
                break;
            case STEP_BUBBLE:
                title = "Le bouton flottant";
                text = "Le bouton flottant reste par-dessus toutes les applis : un appui, et Lisys lit ce qui est affiché "
                        + "(mails, messages, sites).\n\nAppuie sur « Activer » : Android ouvre ses réglages "
                        + "d'accessibilité. Choisis « Lisys : bouton de lecture » (parfois dans « Applis installées »), "
                        + "active-le et accepte. Puis reviens ici avec la flèche retour."
                        + (Build.VERSION.SDK_INT >= 33 ? "\n\nSi Android dit « Paramètre restreint » : appuie sur "
                        + "« Infos appli », puis sur les trois points en haut à droite, puis « Autoriser les paramètres "
                        + "restreints », et recommence." : "");
                addButton(buttons, pal, "Activer", true, new Runnable() {
                    public void run() {
                        Runnable go = new Runnable() {
                            public void run() { sentToSettings = true; MainActivity.openAccessibilitySettings(SetupActivity.this); }
                        };
                        if (Prefs.a11yConsent(SetupActivity.this)) go.run();
                        else MainActivity.showAccessibilityDisclosure(SetupActivity.this, go);
                    }
                });
                if (Build.VERSION.SDK_INT >= 33) {
                    addButton(buttons, pal, "Infos appli (paramètre restreint)", false, new Runnable() {
                        public void run() {
                            try {
                                startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                        Uri.parse("package:" + getPackageName())));
                            } catch (Exception ignored) {
                            }
                        }
                    });
                }
                addButton(buttons, pal, "Passer cette étape", false, new Runnable() { public void run() { next(); } });
                break;
            default:
                title = "C'est prêt !";
                text = "Pour lire :\n• un document : « Ouvrir un document »\n• le courrier : « Lire une photo »\n"
                        + "• la loupe : « Loupe »\n• un site, un mail : la bulle 🔊 (appui long : lecture au doigt)\n\n"
                        + "Dans un texte, appui long sur un paragraphe : répéter lentement ou épeler un mot. "
                        + "Le bouton micro permet de donner des ordres à la voix : « lis », « pause », « suivant »…";
                addButton(buttons, pal, "Commencer", true, new Runnable() { public void run() { finishSetup(); } });
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);
        int p = Ui.dp(this, 22);
        root.setPadding(p, p, p, p);
        TextView stepLabel = Ui.label(this, "Étape " + (step + 1) + " sur 4", 16, pal.muted, false);
        root.addView(stepLabel);
        TextView t = Ui.label(this, title, 30, pal.text, true);
        t.setPadding(0, Ui.dp(this, 6), 0, Ui.dp(this, 14));
        root.addView(t);
        ScrollView sv = new ScrollView(this);
        TextView body = Ui.label(this, text, 21, pal.text, false);
        body.setLineSpacing(0, 1.2f);
        sv.addView(body);
        root.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        root.addView(buttons);
        Ui.setContent(this, root);
        Speaker.say(this, title + ". " + Ui.spoken(text));
    }

    private void addButton(LinearLayout parent, Ui.Palette pal, String text, boolean primary, final Runnable r) {
        Button b = Ui.bigButton(this, text, primary ? pal.button : pal.surface, primary ? pal.buttonText : pal.text);
        b.setGravity(Gravity.CENTER);
        b.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { Ui.tick(v); r.run(); }
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, Ui.dp(this, 10), 0, 0);
        parent.addView(b, lp);
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] perms, int[] res) {
        next();
    }

    @Override
    protected void onPause() {
        Speaker.stop();
        super.onPause();
    }
}
