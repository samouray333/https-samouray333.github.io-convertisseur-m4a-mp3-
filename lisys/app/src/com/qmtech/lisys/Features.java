package com.qmtech.lisys;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;

/**
 * Version gratuite et Lisys Pro. Pro est débloqué par l'appli « clé » payante com.qmtech.lisys.pro
 * (signée avec la même clé), ou pendant les 14 premiers jours d'essai.
 */
final class Features {
    private Features() {}

    static final String PRO_PACKAGE = "com.qmtech.lisys.pro";
    static final int TRIAL_DAYS = 14;

    static boolean keyInstalled(Context c) {
        try {
            PackageManager pm = c.getPackageManager();
            pm.getPackageInfo(PRO_PACKAGE, 0);
            return pm.checkSignatures(c.getPackageName(), PRO_PACKAGE) == PackageManager.SIGNATURE_MATCH;
        } catch (Exception e) {
            return false;
        }
    }

    /** Jours d'essai restants (0 = essai terminé). */
    static int trialDaysLeft(Context c) {
        android.content.SharedPreferences sp = c.getSharedPreferences("reglages", Context.MODE_PRIVATE);
        long first = sp.getLong("firstLaunch", 0);
        if (first == 0) {
            first = System.currentTimeMillis();
            sp.edit().putLong("firstLaunch", first).apply();
        }
        long left = TRIAL_DAYS - (System.currentTimeMillis() - first) / 86400000L;
        return (int) Math.max(0, Math.min(TRIAL_DAYS, left));
    }

    static boolean isPro(Context c) {
        return keyInstalled(c) || trialDaysLeft(c) > 0;
    }

    /** Vrai si la fonction Pro est disponible ; sinon ouvre l'écran « Lisys Pro ». */
    static boolean require(Context c, String feature) {
        if (isPro(c)) return true;
        Intent i = new Intent(c, ProActivity.class).putExtra(ProActivity.EXTRA_FEATURE, feature);
        if (!(c instanceof android.app.Activity)) i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        c.startActivity(i);
        return false;
    }
}
