package com.qmtech.calorys;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.SystemClock;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/**
 * Widget d'écran d'accueil : calories restantes, eau (avec « + 1 verre » sans ouvrir l'appli) et jeûne en cours.
 * L'appli web pousse un résumé du jour (CalorysNative.setWidget) ; les verres ajoutés depuis le widget
 * attendent dans les préférences et sont repris par l'appli à sa prochaine ouverture (takeWidgetWater).
 */
public class CalorysWidget extends AppWidgetProvider {
    static final String PREFS = "widget";
    static final String ACTION_WATER = "com.qmtech.calorys.WIDGET_WATER";

    static String todayKey() { return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date()); }

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) { refresh(ctx); }

    @Override
    public void onReceive(Context ctx, Intent intent) {
        if (ACTION_WATER.equals(intent.getAction())) {
            SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String today = todayKey();
            int pending = today.equals(sp.getString("pendingDate", "")) ? sp.getInt("pendingMl", 0) : 0;
            int glass = 250;
            try { glass = Math.max(50, Math.min(1000, new JSONObject(sp.getString("data", "{}")).optInt("glass", 250))); } catch (Exception e) { /* défaut */ }
            if (pending < 6000) sp.edit().putString("pendingDate", today).putInt("pendingMl", pending + glass).apply();
            refresh(ctx);
            return;
        }
        super.onReceive(ctx, intent);
    }

    /** Résumé envoyé par l'appli : {date, left, goal, water, waterGoal, glass, fastStart, fastGoalH, info}. */
    static void store(Context ctx, String json) {
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putString("data", json).apply();
        refresh(ctx);
    }

    /** Verres ajoutés depuis le widget, à reporter dans le journal : {"date":…,"ml":…} puis remise à zéro. */
    static String takeWater(Context ctx) {
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        int ml = sp.getInt("pendingMl", 0);
        if (ml <= 0) return null;
        String date = sp.getString("pendingDate", "");
        sp.edit().remove("pendingMl").remove("pendingDate").apply();
        return "{\"date\":\"" + date + "\",\"ml\":" + ml + "}";
    }

    static void refresh(Context ctx) {
        AppWidgetManager mgr = AppWidgetManager.getInstance(ctx);
        int[] ids = mgr.getAppWidgetIds(new ComponentName(ctx, CalorysWidget.class));
        if (ids == null || ids.length == 0) return;
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        JSONObject d;
        try { d = new JSONObject(sp.getString("data", "{}")); } catch (Exception e) { d = new JSONObject(); }
        String today = todayKey();
        boolean fresh = today.equals(d.optString("date", ""));
        int pending = today.equals(sp.getString("pendingDate", "")) ? sp.getInt("pendingMl", 0) : 0;

        RemoteViews v = new RemoteViews(ctx.getPackageName(), R.layout.widget);
        if (!d.has("goal")) {
            v.setTextViewText(R.id.w_left, "Calorys");
            v.setTextViewText(R.id.w_left_l, "Ouvre l'appli pour démarrer");
        } else {
            // Nouveau jour sans ouverture de l'appli : rien de mangé, tout l'objectif reste.
            int left = fresh ? d.optInt("left", 0) : d.optInt("goal", 0);
            v.setTextViewText(R.id.w_left, String.format(Locale.FRANCE, "%,d", Math.abs(left)));
            v.setTextViewText(R.id.w_left_l, left < 0 ? "kcal en trop" : "kcal restantes");
        }
        int water = (fresh ? d.optInt("water", 0) : 0) + pending, goal = d.optInt("waterGoal", 2000);
        v.setTextViewText(R.id.w_water, "Eau " + litres(water) + " / " + litres(goal) + " L");
        v.setTextViewText(R.id.w_add, "+ " + (d.optInt("glass", 250)) + " ml");

        long fastStart = d.optLong("fastStart", 0);
        String info = fresh ? d.optString("info", "") : "";
        if (fastStart > 0 && fastStart <= System.currentTimeMillis()) {
            int goalH = d.optInt("fastGoalH", 16);
            v.setViewVisibility(R.id.w_chrono, View.VISIBLE);
            v.setViewVisibility(R.id.w_info, View.GONE);
            v.setChronometer(R.id.w_chrono, SystemClock.elapsedRealtime() - (System.currentTimeMillis() - fastStart), "Jeûne %s / " + goalH + " h", true);
        } else {
            v.setChronometer(R.id.w_chrono, SystemClock.elapsedRealtime(), null, false);
            v.setViewVisibility(R.id.w_chrono, View.GONE);
            v.setViewVisibility(R.id.w_info, info.isEmpty() ? View.GONE : View.VISIBLE);
            v.setTextViewText(R.id.w_info, info);
        }

        Intent open = new Intent(ctx, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(ctx, 700, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        Intent add = new Intent(ctx, CalorysWidget.class).setAction(ACTION_WATER);
        v.setOnClickPendingIntent(R.id.w_add, PendingIntent.getBroadcast(ctx, 701, add, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        mgr.updateAppWidget(ids, v);
    }

    private static String litres(int ml) {
        String s = String.format(Locale.FRANCE, "%.1f", ml / 1000.0);
        return s.endsWith(",0") ? s.substring(0, s.length() - 2) : s;
    }
}
