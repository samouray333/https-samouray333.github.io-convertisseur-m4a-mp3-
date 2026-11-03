package com.qmtech.lisys;

import android.app.Activity;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AdapterView;
import android.widget.TextView;

/**
 * Mode Explorer (sans TalkBack) : un toucher dit le nom du bouton, un deuxième toucher l'active.
 * Glisser le doigt fait défiler normalement.
 */
final class Explorer {
    static final int PASS = 0, CONSUME = 1, INJECT_DOWN = 2;

    private final Activity a;
    private View armed;
    private long armedAt;
    private boolean consuming;
    private float downX, downY;

    Explorer(Activity a) { this.a = a; }

    int dispatch(MotionEvent e) {
        if (!Prefs.explore(a)) return PASS;
        switch (e.getActionMasked()) {
            case MotionEvent.ACTION_DOWN: {
                View v = hit(a.getWindow().getDecorView(), (int) e.getRawX(), (int) e.getRawY());
                long now = SystemClock.uptimeMillis();
                if (v == null || (v == armed && now - armedAt < 4000)) { consuming = false; armed = null; return PASS; }
                consuming = true;
                downX = e.getRawX();
                downY = e.getRawY();
                armed = v;
                armedAt = now;
                String l = label(v);
                Ui.tick(v);
                Speaker.say(a, l.length() > 0 ? l + ". " + Tr.t("Touche encore pour valider.") : Tr.t("Bouton"), null);
                return CONSUME;
            }
            case MotionEvent.ACTION_MOVE:
                if (consuming && Math.hypot(e.getRawX() - downX, e.getRawY() - downY) > Ui.dp(a, 28)) {
                    consuming = false; // c'est un défilement : on rend la main
                    armed = null;
                    return INJECT_DOWN;
                }
                return consuming ? CONSUME : PASS;
            default:
                if (consuming) {
                    if (e.getActionMasked() == MotionEvent.ACTION_UP || e.getActionMasked() == MotionEvent.ACTION_CANCEL) consuming = false;
                    return CONSUME;
                }
                return PASS;
        }
    }

    /** Élément touchable le plus haut sous le doigt. */
    private static View hit(View v, int x, int y) {
        if (v.getVisibility() != View.VISIBLE) return null;
        int[] loc = new int[2];
        v.getLocationOnScreen(loc);
        if (x < loc[0] || y < loc[1] || x >= loc[0] + v.getWidth() || y >= loc[1] + v.getHeight()) return null;
        if (v instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) v;
            for (int i = g.getChildCount() - 1; i >= 0; i--) {
                View r = hit(g.getChildAt(i), x, y);
                if (r != null) return r;
            }
        }
        if (v.isClickable() || v.isLongClickable() || v.getParent() instanceof AdapterView) return v;
        return null;
    }

    static String label(View v) {
        CharSequence d = v.getContentDescription();
        if (d != null && d.length() > 0) return Ui.spoken(d.toString());
        StringBuilder sb = new StringBuilder();
        collect(v, sb);
        return Ui.spoken(sb.toString());
    }

    private static void collect(View v, StringBuilder sb) {
        if (v instanceof TextView) {
            CharSequence t = ((TextView) v).getText();
            if (t != null && t.length() > 0) sb.append(t).append(". ");
        } else if (v instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) v;
            for (int i = 0; i < g.getChildCount(); i++) collect(g.getChildAt(i), sb);
        }
    }
}
