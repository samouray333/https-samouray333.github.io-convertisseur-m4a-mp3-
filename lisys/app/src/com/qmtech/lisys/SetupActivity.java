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
    private boolean resumed;
    private int retries;
    private static final int REQ_VOICE = 5;

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
        resumed = true;
        // Retour des réglages d'Android : on vérifie tout seul si le bouton flottant est activé.
        if (step == STEP_BUBBLE && sentToSettings) {
            sentToSettings = false;
            if (ScreenReaderService.isEnabled(this)) { step = STEP_DONE; show(); }
            else Speaker.say(this, Tr.t("Le bouton flottant n'est pas encore activé. Tu peux réessayer, ou passer cette étape."));
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
                title = Tr.t("Bienvenue dans Lisys");
                text = Tr.t("Lisys lit à voix haute tes documents, les pages web, le courrier en photo, et tout ce qui est ")
                        + Tr.t("affiché sur le téléphone.\n\nAvant de commencer, choisis un affichage confortable. ")
                        + Tr.t("Tu pourras tout changer plus tard dans les réglages.");
                addButton(buttons, pal, Prefs.theme(this) == Prefs.THEME_CONTRASTE ? Tr.t("Affichage normal (noir sur blanc)")
                        : Tr.t("Contraste élevé (jaune sur noir)"), false, new Runnable() {
                    public void run() {
                        Prefs.setTheme(SetupActivity.this, Prefs.theme(SetupActivity.this) == Prefs.THEME_CONTRASTE
                                ? Prefs.THEME_CLAIR : Prefs.THEME_CONTRASTE);
                        show();
                    }
                });
                addButton(buttons, pal, Prefs.bigControls(this) ? Tr.t("Boutons normaux") : Tr.t("Boutons géants"), false, new Runnable() {
                    public void run() { Prefs.setBigControls(SetupActivity.this, !Prefs.bigControls(SetupActivity.this)); show(); }
                });
                addButton(buttons, pal, Tr.t("Continuer"), true, new Runnable() { public void run() { next(); } });
                break;
            case STEP_NOTIF:
                title = Tr.t("Notifications");
                text = Tr.t("Lisys affiche les commandes de lecture (pause, phrase suivante) dans les notifications et sur ")
                        + Tr.t("l'écran verrouillé. Appuie sur « Autoriser », puis accepte dans la fenêtre d'Android.");
                addButton(buttons, pal, Tr.t("Autoriser"), true, new Runnable() {
                    public void run() { requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1); }
                });
                addButton(buttons, pal, Tr.t("Passer"), false, new Runnable() { public void run() { next(); } });
                break;
            case STEP_BUBBLE:
                title = Tr.t("Le bouton flottant");
                text = Tr.t("Le bouton flottant reste par-dessus toutes les applis : un appui, et Lisys lit ce qui est affiché ")
                        + Tr.t("(mails, messages, sites).\n\nAppuie sur « Activer » : Android ouvre ses réglages ")
                        + Tr.t("d'accessibilité. Choisis « Lisys : bouton de lecture » (parfois dans « Applis installées »), ")
                        + Tr.t("active-le et accepte. Puis reviens ici avec la flèche retour.")
                        + (Build.VERSION.SDK_INT >= 33 ? Tr.t("\n\nSi Android dit « Paramètre restreint » : appuie sur ")
                        + Tr.t("« Infos appli », puis sur les trois points en haut à droite, puis « Autoriser les paramètres ")
                        + Tr.t("restreints », et recommence.") : "");
                addButton(buttons, pal, Tr.t("Activer"), true, new Runnable() { public void run() { activateBubble(); } });
                if (Build.VERSION.SDK_INT >= 33) {
                    addButton(buttons, pal, Tr.t("Infos appli (paramètre restreint)"), false, new Runnable() {
                        public void run() {
                            try {
                                startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                        Uri.parse("package:" + getPackageName())));
                            } catch (Exception ignored) {
                            }
                        }
                    });
                }
                addButton(buttons, pal, Tr.t("Passer cette étape"), false, new Runnable() { public void run() { next(); } });
                break;
            default:
                title = Tr.t("C'est prêt !");
                text = Tr.t("Pour lire :\n• un document : « Ouvrir un document »\n• le courrier : « Lire une photo »\n")
                        + Tr.t("• la loupe : « Loupe »\n• un site, un mail : la bulle 🔊 (appui long : lecture au doigt)\n\n")
                        + Tr.t("Dans un texte, appui long sur un paragraphe : répéter lentement ou épeler un mot. ")
                        + Tr.t("Le bouton micro permet de donner des ordres à la voix : « lis », « pause », « suivant »…");
                addButton(buttons, pal, Tr.t("Commencer"), true, new Runnable() { public void run() { finishSetup(); } });
        }

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);
        int p = Ui.dp(this, 22);
        root.setPadding(p, p, p, p);
        TextView stepLabel = Ui.label(this, Tr.t("Étape ") + (step + 1) + Tr.t(" sur 4"), 16, pal.muted, false);
        root.addView(stepLabel);
        TextView t = Ui.label(this, title, 30, pal.text, true);
        t.setPadding(0, Ui.dp(this, 6), 0, Ui.dp(this, 14));
        root.addView(t);
        ScrollView sv = new ScrollView(this);
        TextView body = Ui.label(this, text, 21, pal.text, false);
        body.setLineSpacing(0, 1.2f);
        sv.addView(body);
        root.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        addButton(buttons, pal, Tr.t("🎤   Répondre à voix haute"), false, new Runnable() { public void run() { listen(); } });
        root.addView(buttons);
        Ui.setContent(this, root);
        retries = 0;
        // Tout est lu à voix haute, puis Lisys écoute la réponse (« oui », « non », « répète »…).
        Speaker.say(this, title + ". " + Ui.spoken(text) + " " + question(), new Runnable() {
            public void run() { if (resumed && !isFinishing() && Prefs.voiceAnswers(SetupActivity.this)) listen(); }
        });
    }

    private String question() {
        switch (step) {
            case STEP_WELCOME: return Tr.t("Dis « oui » pour continuer, « contraste » pour le jaune sur noir, « gros boutons », ou « répète ».");
            case STEP_NOTIF: return Tr.t("Dis « oui » pour autoriser, ou « non » pour passer.");
            case STEP_BUBBLE: return Tr.t("Dis « oui » pour activer le bouton flottant, ou « non » pour passer.");
            default: return Tr.t("Dis « oui » pour commencer.");
        }
    }

    private void listen() {
        VoiceCommands.listen(this, REQ_VOICE, question());
    }

    private void activateBubble() {
        final Runnable go = new Runnable() {
            public void run() {
                sentToSettings = true;
                Speaker.say(SetupActivity.this, Tr.t("J'ouvre les réglages d'Android. Choisis « Lisys : bouton de lecture », active-le, accepte, puis reviens avec la flèche retour."),
                        new Runnable() { public void run() { MainActivity.openAccessibilitySettings(SetupActivity.this); } });
            }
        };
        if (Prefs.a11yConsent(this)) { go.run(); return; }
        Speaker.say(this, Tr.t("Une fenêtre explique ce que Lisys lit à l'écran : seulement quand tu le demandes, et rien ne quitte ")
                + Tr.t("le téléphone. Appuie sur le bouton « J'accepte », en bas à droite de la fenêtre."));
        MainActivity.showAccessibilityDisclosure(this, go);
    }

    private static final String[] YES = {"oui", "ouais", "ok", "okay", "daccord", "accord", "continuer", "continue", "suivant",
            "vas", "commencer", "commence", "active", "activer", "autoriser", "autorise", "accepte", "go"};
    private static final String[] NO = {"non", "passer", "passe", "plus", "tard", "suivante", "ignore", "pas"};

    private void answer(String raw) {
        if (raw == null) return;
        String c = VoiceCommands.norm(raw).replace("d accord", "daccord");
        if (VoiceCommands.has(c, "repete", "repeter", "quoi", "comment", "pardon", "encore")) { show(); return; }
        boolean yes = VoiceCommands.has(c, YES), no = VoiceCommands.has(c, NO) && !yes;
        switch (step) {
            case STEP_WELCOME:
                if (VoiceCommands.has(c, "contraste", "jaune", "noir", "normal")) {
                    Prefs.setTheme(this, Prefs.theme(this) == Prefs.THEME_CONTRASTE ? Prefs.THEME_CLAIR : Prefs.THEME_CONTRASTE);
                    show();
                    return;
                }
                if (VoiceCommands.has(c, "gros", "geant", "geants", "boutons", "grand")) {
                    Prefs.setBigControls(this, !Prefs.bigControls(this));
                    show();
                    return;
                }
                if (yes || no) { next(); return; }
                break;
            case STEP_NOTIF:
                if (yes) { requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 1); return; }
                if (no) { next(); return; }
                break;
            case STEP_BUBBLE:
                if (VoiceCommands.has(c, "restreint", "infos", "info")) {
                    try {
                        startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName())));
                    } catch (Exception ignored) {
                    }
                    return;
                }
                if (yes) { activateBubble(); return; }
                if (no) { next(); return; }
                break;
            default:
                if (yes || no) { finishSetup(); return; }
        }
        // Pas compris : on redemande (deux fois au plus, ensuite les boutons restent là).
        if (retries++ < 2) {
            Speaker.say(this, Tr.t("Je n'ai pas compris « ") + raw + " ». " + question(), new Runnable() {
                public void run() { if (resumed && !isFinishing()) listen(); }
            });
        } else {
            Speaker.say(this, Tr.t("Tu peux aussi appuyer sur les gros boutons en bas de l'écran."));
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_VOICE && res == RESULT_OK) answer(VoiceCommands.heard(data));
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
        resumed = false;
        Speaker.stop();
        super.onPause();
    }
}
