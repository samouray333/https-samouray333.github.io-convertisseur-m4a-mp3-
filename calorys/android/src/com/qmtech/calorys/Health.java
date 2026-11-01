package com.qmtech.calorys;

import android.annotation.TargetApi;
import android.content.Context;
import android.health.connect.HealthConnectException;
import android.health.connect.HealthConnectManager;
import android.health.connect.ReadRecordsRequestUsingFilters;
import android.health.connect.ReadRecordsResponse;
import android.health.connect.TimeInstantRangeFilter;
import android.health.connect.datatypes.BodyFatRecord;
import android.health.connect.datatypes.WeightRecord;
import android.os.Build;
import android.os.OutcomeReceiver;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.Instant;

/**
 * Pesées des balances connectées via Health Connect (intégré à Android 14 et plus).
 * Les applis de balance (Fitdays, Renpho, Withings, Zepp, Huawei Santé, Fitbit…) y écrivent
 * le poids et la masse grasse ; Calorys ne fait que lire, et tout reste sur le téléphone.
 * Toutes les références à android.health.connect sont ici, appelées seulement si available().
 */
@TargetApi(34)
final class Health {
    interface Done { void done(String json); }

    static final String READ_WEIGHT = "android.permission.health.READ_WEIGHT";
    static final String READ_BODY_FAT = "android.permission.health.READ_BODY_FAT";
    static final String READ_HISTORY = "android.permission.health.READ_HEALTH_DATA_HISTORY";

    private Health() {}

    static boolean available(Context c) {
        try { return Build.VERSION.SDK_INT >= 34 && c.getSystemService(HealthConnectManager.class) != null; }
        catch (Throwable t) { return false; }
    }

    static String[] permissions() {
        return Build.VERSION.SDK_INT >= 35 ? new String[]{READ_WEIGHT, READ_BODY_FAT, READ_HISTORY} : new String[]{READ_WEIGHT, READ_BODY_FAT};
    }

    /** Lit poids et masse grasse depuis sinceMs : {"weights":[{t,kg,src}],"fats":[{t,pct,src}]} ou {"error":…}. */
    static void read(Context c, long sinceMs, final Done cb) {
        final HealthConnectManager m = c.getSystemService(HealthConnectManager.class);
        final Instant start = Instant.ofEpochMilli(Math.max(0, sinceMs)), end = Instant.now();
        final JSONArray weights = new JSONArray(), fats = new JSONArray();
        readWeights(c, m, start, end, -1, weights, new Runnable() {
            @Override
            public void run() {
                // La masse grasse est facultative : sans autorisation, on renvoie juste le poids.
                readFats(c, m, start, end, -1, fats, new Runnable() {
                    @Override
                    public void run() {
                        try {
                            JSONObject o = new JSONObject();
                            o.put("weights", weights);
                            o.put("fats", fats);
                            cb.done(o.toString());
                        } catch (Exception e) { cb.done("{\"error\":\"json\"}"); }
                    }
                });
            }
        }, cb);
    }

    private static TimeInstantRangeFilter range(Instant a, Instant b) {
        return new TimeInstantRangeFilter.Builder().setStartTime(a).setEndTime(b).build();
    }

    private static void readWeights(final Context c, final HealthConnectManager m, final Instant a, final Instant b, long token,
                                    final JSONArray out, final Runnable next, final Done fail) {
        ReadRecordsRequestUsingFilters.Builder<WeightRecord> rb = new ReadRecordsRequestUsingFilters.Builder<>(WeightRecord.class)
                .setTimeRangeFilter(range(a, b)).setPageSize(1000);
        if (token > 0) rb.setPageToken(token);
        m.readRecords(rb.build(), c.getMainExecutor(), new OutcomeReceiver<ReadRecordsResponse<WeightRecord>, HealthConnectException>() {
            @Override
            public void onResult(ReadRecordsResponse<WeightRecord> r) {
                try {
                    for (WeightRecord w : r.getRecords()) {
                        if (c.getPackageName().equals(w.getMetadata().getDataOrigin().getPackageName())) continue;
                        JSONObject o = new JSONObject();
                        o.put("t", w.getTime().toEpochMilli());
                        o.put("kg", w.getWeight().getInGrams() / 1000.0);
                        o.put("src", w.getMetadata().getDataOrigin().getPackageName());
                        out.put(o);
                    }
                } catch (Exception e) { /* enregistrement ignoré */ }
                if (r.getNextPageToken() > 0 && out.length() < 20000) readWeights(c, m, a, b, r.getNextPageToken(), out, next, fail);
                else next.run();
            }

            @Override
            public void onError(HealthConnectException e) {
                fail.done("{\"error\":" + JSONObject.quote(String.valueOf(e.getMessage())) + "}");
            }
        });
    }

    private static void readFats(final Context c, final HealthConnectManager m, final Instant a, final Instant b, long token,
                                 final JSONArray out, final Runnable next) {
        try {
            ReadRecordsRequestUsingFilters.Builder<BodyFatRecord> rb = new ReadRecordsRequestUsingFilters.Builder<>(BodyFatRecord.class)
                    .setTimeRangeFilter(range(a, b)).setPageSize(1000);
            if (token > 0) rb.setPageToken(token);
            m.readRecords(rb.build(), c.getMainExecutor(), new OutcomeReceiver<ReadRecordsResponse<BodyFatRecord>, HealthConnectException>() {
                @Override
                public void onResult(ReadRecordsResponse<BodyFatRecord> r) {
                    try {
                        for (BodyFatRecord f : r.getRecords()) {
                            JSONObject o = new JSONObject();
                            o.put("t", f.getTime().toEpochMilli());
                            o.put("pct", f.getPercentage().getValue());
                            o.put("src", f.getMetadata().getDataOrigin().getPackageName());
                            out.put(o);
                        }
                    } catch (Exception e) { /* enregistrement ignoré */ }
                    if (r.getNextPageToken() > 0 && out.length() < 20000) readFats(c, m, a, b, r.getNextPageToken(), out, next);
                    else next.run();
                }

                @Override
                public void onError(HealthConnectException e) { next.run(); }
            });
        } catch (Throwable t) { next.run(); }
    }
}
