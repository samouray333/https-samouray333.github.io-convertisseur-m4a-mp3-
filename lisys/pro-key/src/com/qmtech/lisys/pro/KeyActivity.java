package com.qmtech.lisys.pro;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Écran de la clé Lisys Pro : confirme l'activation et ouvre Lisys. */
public class KeyActivity extends Activity {
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setBackgroundColor(0xFF1E3A8A);
        int p = (int) (24 * getResources().getDisplayMetrics().density);
        root.setPadding(p, p, p, p);
        TextView t = new TextView(this);
        t.setText("✅ Lisys Pro est activé.\n\nMerci ! Toutes les fonctions de Lisys sont débloquées. "
                + "Garde cette appli installée : c'est ta clé.");
        t.setTextColor(0xFFFFFFFF);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
        t.setGravity(Gravity.CENTER);
        root.addView(t);
        Button open = new Button(this);
        open.setText("Ouvrir Lisys");
        open.setTextSize(TypedValue.COMPLEX_UNIT_SP, 22);
        open.setAllCaps(false);
        open.setOnClickListener(new android.view.View.OnClickListener() {
            @Override public void onClick(android.view.View v) {
                Intent i = getPackageManager().getLaunchIntentForPackage("com.qmtech.lisys");
                if (i == null) i = new Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=com.qmtech.lisys"));
                try { startActivity(i); } catch (Exception ignored) {}
                finish();
            }
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.topMargin = p;
        root.addView(open, lp);
        setContentView(root);
    }
}
