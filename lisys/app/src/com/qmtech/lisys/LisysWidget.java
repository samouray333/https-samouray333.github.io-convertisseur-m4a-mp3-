package com.qmtech.lisys;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/** Widget de l'écran d'accueil : trois gros boutons (photo, texte copié, loupe). */
public class LisysWidget extends AppWidgetProvider {

    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) {
        RemoteViews rv = new RemoteViews(c.getPackageName(), R.layout.widget);
        rv.setOnClickPendingIntent(R.id.w_photo, open(c, 1, new Intent(c, OcrActivity.class)
                .putExtra(OcrActivity.EXTRA_MODE, OcrActivity.MODE_CAMERA)));
        rv.setOnClickPendingIntent(R.id.w_clip, open(c, 2, new Intent(c, MainActivity.class)
                .setAction(MainActivity.ACTION_READ_CLIPBOARD)));
        rv.setOnClickPendingIntent(R.id.w_loupe, open(c, 3, new Intent(c, MagnifierActivity.class)));
        for (int id : ids) m.updateAppWidget(id, rv);
    }

    static PendingIntent open(Context c, int code, Intent i) {
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(c, code, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }
}
