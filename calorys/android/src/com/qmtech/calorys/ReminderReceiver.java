package com.qmtech.calorys;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Calendar;

/**
 * Rappels de Calorys : repas, eau, pesée (quotidiens) et fin du jeûne (ponctuel).
 * Le plan vient de l'appli web (CalorysNative.setReminders) et survit au redémarrage.
 */
public class ReminderReceiver extends BroadcastReceiver {
    static final String CHANNEL = "rappels";
    static final String ACTION = "com.qmtech.calorys.REMINDER";
    static final String PREFS = "reminders";
    static final int FAST_ID = 99;

    @Override
    public void onReceive(Context ctx, Intent intent) {
        String a = intent.getAction();
        if (Intent.ACTION_BOOT_COMPLETED.equals(a) || Intent.ACTION_MY_PACKAGE_REPLACED.equals(a)) {
            schedule(ctx, ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString("plan", null));
            return;
        }
        if (!ACTION.equals(a)) return;
        int id = intent.getIntExtra("id", 0);
        notify(ctx, id, intent.getStringExtra("title"), intent.getStringExtra("text"));
        // Les rappels quotidiens se reprogramment pour le lendemain (alarmes inexactes, économes en batterie).
        if (id != FAST_ID) {
            String at = intent.getStringExtra("at");
            if (at != null) set(ctx, id, at, intent.getStringExtra("title"), intent.getStringExtra("text"), next(at, true));
        }
    }

    static void notify(Context ctx, int id, String title, String text) {
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Rappels", NotificationManager.IMPORTANCE_DEFAULT);
            ch.setDescription("Repas, eau, pesée et fin du jeûne");
            nm.createNotificationChannel(ch);
        }
        Intent open = new Intent(ctx, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(ctx, id, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(ctx, CHANNEL)
                .setSmallIcon(R.drawable.ic_notif)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setColor(0xFF0F9F6E)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .build();
        try { nm.notify(id, n); } catch (SecurityException e) { /* notifications refusées */ }
    }

    /** Applique un plan JSON {daily:[{id,at,title,text}], fastEnd: ms}. */
    static void schedule(Context ctx, String json) {
        SharedPreferences sp = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        // Annule les anciens rappels.
        String old = sp.getString("ids", "");
        for (String s : old.split(",")) if (!s.isEmpty()) cancel(ctx, Integer.parseInt(s));
        cancel(ctx, FAST_ID);
        StringBuilder ids = new StringBuilder();
        if (json != null) {
            try {
                JSONObject plan = new JSONObject(json);
                JSONArray daily = plan.optJSONArray("daily");
                if (daily != null) for (int i = 0; i < daily.length(); i++) {
                    JSONObject r = daily.getJSONObject(i);
                    int id = r.getInt("id");
                    set(ctx, id, r.getString("at"), r.getString("title"), r.getString("text"), next(r.getString("at"), false));
                    ids.append(id).append(',');
                }
                long fastEnd = plan.optLong("fastEnd", 0);
                if (fastEnd > System.currentTimeMillis()) {
                    Intent it = new Intent(ctx, ReminderReceiver.class).setAction(ACTION)
                            .putExtra("id", FAST_ID).putExtra("title", "Jeûne terminé").putExtra("text", "Objectif atteint : tu peux rompre le jeûne. Bravo !");
                    PendingIntent pi = PendingIntent.getBroadcast(ctx, FAST_ID, it, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
                    AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
                    if (am != null) am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, fastEnd, pi);
                }
            } catch (Exception e) { /* plan invalide */ }
        }
        sp.edit().putString("plan", json).putString("ids", ids.toString()).apply();
    }

    static void set(Context ctx, int id, String at, String title, String text, long when) {
        Intent it = new Intent(ctx, ReminderReceiver.class).setAction(ACTION)
                .putExtra("id", id).putExtra("at", at).putExtra("title", title).putExtra("text", text);
        PendingIntent pi = PendingIntent.getBroadcast(ctx, id, it, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
        if (am != null) am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, when, pi);
    }

    static void cancel(Context ctx, int id) {
        Intent it = new Intent(ctx, ReminderReceiver.class).setAction(ACTION);
        PendingIntent pi = PendingIntent.getBroadcast(ctx, id, it, PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
        AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
        if (pi != null && am != null) { am.cancel(pi); pi.cancel(); }
    }

    /** Prochaine occurrence de HH:MM (demain si l'heure est passée, ou si forceTomorrow). */
    static long next(String at, boolean forceTomorrow) {
        String[] hm = at.split(":");
        Calendar c = Calendar.getInstance();
        c.set(Calendar.HOUR_OF_DAY, Integer.parseInt(hm[0]));
        c.set(Calendar.MINUTE, Integer.parseInt(hm[1]));
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        if (forceTomorrow || c.getTimeInMillis() <= System.currentTimeMillis() + 30000) c.add(Calendar.DAY_OF_YEAR, 1);
        return c.getTimeInMillis();
    }
}
