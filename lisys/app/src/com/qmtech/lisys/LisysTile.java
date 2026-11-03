package com.qmtech.lisys;

import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/** Raccourci dans le menu du haut d'Android : « Lisys : lire l'écran ». */
public class LisysTile extends TileService {

    @Override
    public void onStartListening() {
        Tile t = getQsTile();
        if (t == null) return;
        t.setState(Tile.STATE_ACTIVE);
        t.updateTile();
    }

    @Override
    public void onClick() {
        ScreenReaderService s = ScreenReaderService.instance;
        if (s != null) {
            // Le bouton flottant est activé : on ferme le menu du haut puis on lit l'écran dessous.
            s.readScreenFromShade();
            return;
        }
        Intent i = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(PendingIntent.getActivity(this, 0, i, PendingIntent.FLAG_IMMUTABLE));
        } else {
            startActivityAndCollapse(i);
        }
    }
}
