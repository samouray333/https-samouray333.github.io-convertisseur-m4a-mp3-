package com.qmtech.lisys;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/** Présentation de Lisys Pro, en gros caractères et lue à voix haute. */
public class ProActivity extends Activity {

    static final String EXTRA_FEATURE = "feature";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        Ui.Palette pal = Ui.palette(this);
        Ui.systemBars(this, pal);
        String feature = getIntent().getStringExtra(EXTRA_FEATURE);
        boolean pro = Features.keyInstalled(this);
        int trial = Features.trialDaysLeft(this);
        String status = pro ? Tr.t("✅ Lisys Pro est activé. Merci !")
                : trial > 0 ? Tr.t("Essai gratuit : encore ") + trial + Tr.t(" jour") + (trial > 1 ? "s" : "") + Tr.t(" avec toutes les fonctions.")
                : (feature != null ? "« " + feature + Tr.t(" » fait partie de Lisys Pro.") : Tr.t("L'essai gratuit est terminé."));
        String text = status + Tr.t("\n\nLisys gratuit lit tes documents (PDF, Word, livres, DAISY), les pages web et le texte copié, ")
                + Tr.t("avec tous les réglages de confort.\n\nLisys Pro ajoute, pour toujours, en un seul achat :\n")
                + Tr.t("• le bouton flottant pour lire les autres applis, la lecture au doigt, le bandeau en gros texte, ")
                + Tr.t("les boutons de volume et l'annonce des messages\n• la lecture des photos, du courrier et des PDF scannés\n")
                + Tr.t("• la loupe et la lecture des codes-barres des produits\n• la création de fichiers audio\n\n")
                + Tr.t("Pour l'avoir : installe « Lisys Pro » depuis le Play Store. Rien à régler : Lisys se débloque tout seul.");

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);
        int p = Ui.dp(this, 22);
        root.setPadding(p, p, p, p);
        root.addView(Ui.label(this, "Lisys Pro", 32, pal.text, true));
        ScrollView sv = new ScrollView(this);
        TextView body = Ui.label(this, text, 20, pal.text, false);
        body.setLineSpacing(0, 1.2f);
        body.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 12));
        sv.addView(body);
        root.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        if (!pro) {
            Button buy = Ui.bigButton(this, Tr.t("Obtenir Lisys Pro"), pal.button, pal.buttonText);
            buy.setGravity(Gravity.CENTER);
            buy.setOnClickListener(new View.OnClickListener() {
                @Override public void onClick(View v) {
                    try {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=" + Features.PRO_PACKAGE)));
                    } catch (Exception e) {
                        startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/store/apps/details?id=" + Features.PRO_PACKAGE)));
                    }
                }
            });
            root.addView(buy, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        }
        Button back = Ui.bigButton(this, Tr.t("Retour"), pal.surface, pal.text);
        back.setGravity(Gravity.CENTER);
        back.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { finish(); } });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, Ui.dp(this, 10), 0, 0);
        root.addView(back, lp);
        Ui.setContent(this, root);
        Speaker.say(this, Ui.spoken(text));
    }

    @Override
    protected void onPause() {
        Speaker.stop();
        super.onPause();
    }
}
