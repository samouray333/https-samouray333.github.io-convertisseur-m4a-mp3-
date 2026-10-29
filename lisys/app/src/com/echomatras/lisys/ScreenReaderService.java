package com.echomatras.lisys;

import android.accessibilityservice.AccessibilityButtonController;
import android.accessibilityservice.AccessibilityService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

/**
 * Bouton flottant « Lisys » par-dessus toutes les applis :
 * un appui lit ce qui est affiché (site web, appli, message…),
 * un appui long permet de toucher l'endroit où commencer la lecture.
 */
public class ScreenReaderService extends AccessibilityService implements ReaderService.Listener {

    static final String SOURCE = "ecran";
    static final String TITLE = "Lecture de l'écran";

    /** Un bloc de texte vu à l'écran, avec sa position. */
    static final class Item {
        final String text;
        final Rect bounds;
        final boolean visible;
        Item(String t, Rect b, boolean v) { text = t; bounds = b; visible = v; }
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private WindowManager wm;
    private TextView bubble;
    private WindowManager.LayoutParams bubbleLp;
    private FrameLayout touchLayer;
    private List<Item> snapshot;
    private String snapshotApp;
    private ReaderService reader;
    private boolean bound;
    private AccessibilityButtonController.AccessibilityButtonCallback buttonCallback;

    private final ServiceConnection conn = new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName n, IBinder b) {
            reader = ((ReaderService.LocalBinder) b).service();
            reader.addListener(ScreenReaderService.this);
        }
        @Override public void onServiceDisconnected(ComponentName n) { reader = null; }
    };

    private final SharedPreferences.OnSharedPreferenceChangeListener prefsListener =
            new SharedPreferences.OnSharedPreferenceChangeListener() {
                @Override public void onSharedPreferenceChanged(SharedPreferences sp, String key) {
                    if ("bubble".equals(key)) {
                        if (Prefs.bubble(ScreenReaderService.this)) showBubble();
                        else hideBubble();
                    }
                }
            };

    // ------------------------------------------------------------------ cycle de vie

    @Override
    protected void onServiceConnected() {
        super.onServiceConnected();
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        bound = bindService(new Intent(this, ReaderService.class), conn, Context.BIND_AUTO_CREATE);
        getSharedPreferences("reglages", MODE_PRIVATE).registerOnSharedPreferenceChangeListener(prefsListener);
        if (Prefs.bubble(this)) showBubble();
        // Bouton d'accessibilité d'Android (barre de navigation ou geste) : même action que la bulle.
        try {
            buttonCallback = new AccessibilityButtonController.AccessibilityButtonCallback() {
                @Override public void onClicked(AccessibilityButtonController c) { readScreen(); }
            };
            getAccessibilityButtonController().registerAccessibilityButtonCallback(buttonCallback, main);
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // Rien à faire en continu : on ne lit l'écran que quand on appuie sur le bouton.
    }

    @Override
    public void onInterrupt() {
        if (reader != null && isScreenDoc()) reader.pause();
    }

    @Override
    public void onDestroy() {
        getSharedPreferences("reglages", MODE_PRIVATE).unregisterOnSharedPreferenceChangeListener(prefsListener);
        hideTouchLayer();
        hideBubble();
        try {
            if (buttonCallback != null) getAccessibilityButtonController().unregisterAccessibilityButtonCallback(buttonCallback);
        } catch (Exception ignored) {
        }
        if (reader != null) reader.removeListener(this);
        if (bound) {
            try { unbindService(conn); } catch (Exception ignored) {}
            bound = false;
        }
        super.onDestroy();
    }

    /** Le bouton est-il activé dans les réglages d'accessibilité ? */
    static boolean isEnabled(Context c) {
        String list = Settings.Secure.getString(c.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
        if (list == null) return false;
        ComponentName me = new ComponentName(c, ScreenReaderService.class);
        for (String s : list.split(":")) {
            ComponentName cn = ComponentName.unflattenFromString(s);
            if (me.equals(cn)) return true;
        }
        return false;
    }

    // ------------------------------------------------------------------ bulle flottante

    private void showBubble() {
        if (bubble != null || wm == null) return;
        int size = Ui.dp(this, 58);
        bubble = new TextView(this);
        bubble.setText("🔊");
        bubble.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24);
        bubble.setGravity(Gravity.CENTER);
        bubble.setTypeface(Typeface.DEFAULT_BOLD);
        bubble.setTextColor(0xFFFFFFFF);
        bubble.setContentDescription("Lisys : lire l'écran. Appui long : toucher l'endroit où commencer.");
        GradientDrawable d = new GradientDrawable();
        d.setShape(GradientDrawable.OVAL);
        d.setColor(Ui.BRAND);
        d.setStroke(Ui.dp(this, 3), 0xFFFFFFFF);
        bubble.setBackground(d);
        bubble.setElevation(Ui.dp(this, 6));
        bubble.setAlpha(0.92f);

        DisplayMetrics dm = getResources().getDisplayMetrics();
        bubbleLp = new WindowManager.LayoutParams(size, size,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        bubbleLp.gravity = Gravity.TOP | Gravity.START;
        int x = Prefs.bubbleX(this), y = Prefs.bubbleY(this);
        bubbleLp.x = x >= 0 ? Math.min(x, dm.widthPixels - size) : dm.widthPixels - size - Ui.dp(this, 8);
        bubbleLp.y = y >= 0 ? Math.min(y, dm.heightPixels - size) : dm.heightPixels / 2;
        bubble.setOnTouchListener(new BubbleTouch());
        try {
            wm.addView(bubble, bubbleLp);
        } catch (Exception e) {
            bubble = null;
        }
    }

    private void hideBubble() {
        if (bubble != null) {
            try { wm.removeView(bubble); } catch (Exception ignored) {}
            bubble = null;
        }
    }

    /** Appui = lire, appui long = toucher pour lire, glisser = déplacer la bulle. */
    private final class BubbleTouch implements View.OnTouchListener {
        private float downX, downY;
        private int startX, startY;
        private boolean dragging, longDone;
        private final int slop = ViewConfiguration.get(ScreenReaderService.this).getScaledTouchSlop();
        private final Runnable longPress = new Runnable() {
            @Override public void run() {
                longDone = true;
                bubble.performHapticFeedback(android.view.HapticFeedbackConstants.LONG_PRESS);
                startTouchMode();
            }
        };

        @Override
        public boolean onTouch(View v, MotionEvent e) {
            switch (e.getActionMasked()) {
                case MotionEvent.ACTION_DOWN:
                    downX = e.getRawX();
                    downY = e.getRawY();
                    startX = bubbleLp.x;
                    startY = bubbleLp.y;
                    dragging = false;
                    longDone = false;
                    main.postDelayed(longPress, ViewConfiguration.getLongPressTimeout());
                    return true;
                case MotionEvent.ACTION_MOVE:
                    if (longDone) return true;
                    float dx = e.getRawX() - downX, dy = e.getRawY() - downY;
                    if (!dragging && Math.hypot(dx, dy) > slop) {
                        dragging = true;
                        main.removeCallbacks(longPress);
                    }
                    if (dragging) {
                        bubbleLp.x = Math.max(0, (int) (startX + dx));
                        bubbleLp.y = Math.max(0, (int) (startY + dy));
                        try { wm.updateViewLayout(bubble, bubbleLp); } catch (Exception ignored) {}
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                    main.removeCallbacks(longPress);
                    if (dragging) {
                        snapToEdge();
                        Prefs.setBubblePos(ScreenReaderService.this, bubbleLp.x, bubbleLp.y);
                    } else if (!longDone) {
                        readScreen();
                    }
                    return true;
                case MotionEvent.ACTION_CANCEL:
                    main.removeCallbacks(longPress);
                    return true;
            }
            return false;
        }
    }

    private void snapToEdge() {
        DisplayMetrics dm = getResources().getDisplayMetrics();
        int size = bubbleLp.width;
        int margin = Ui.dp(this, 4);
        bubbleLp.x = bubbleLp.x + size / 2 < dm.widthPixels / 2 ? margin : dm.widthPixels - size - margin;
        bubbleLp.y = Math.min(bubbleLp.y, dm.heightPixels - size - margin);
        try { wm.updateViewLayout(bubble, bubbleLp); } catch (Exception ignored) {}
    }

    private void setBubblePlaying(boolean playing) {
        if (bubble == null) return;
        bubble.setText(playing ? "⏹" : "🔊");
        bubble.setContentDescription(playing ? "Lisys : arrêter la lecture" : "Lisys : lire l'écran");
    }

    // ------------------------------------------------------------------ lecture de l'écran

    private boolean isScreenDoc() {
        return reader != null && reader.docId() != null
                && reader.docId().equals(Library.makeId(SOURCE, TITLE));
    }

    /** Appui sur la bulle : lit l'écran, ou arrête si on est déjà en train de le lire. */
    void readScreen() {
        if (reader == null) {
            Toast.makeText(this, "Lisys démarre, réessaie dans une seconde.", Toast.LENGTH_SHORT).show();
            return;
        }
        if (reader.isPlaying() && isScreenDoc()) {
            reader.pause();
            return;
        }
        hideTouchLayer();
        String app = currentAppLabel();
        List<Item> items = collect();
        if (items.isEmpty()) {
            Toast.makeText(this, "Aucun texte à lire sur cet écran.", Toast.LENGTH_SHORT).show();
            return;
        }
        // On commence au premier texte visible ; la suite (bas d'une page web) est lue ensuite.
        int start = 0;
        for (int i = 0; i < items.size(); i++) {
            if (items.get(i).visible) { start = i; break; }
        }
        play(items, start, app);
    }

    private void play(List<Item> items, int start, String app) {
        Extractor.Result r = new Extractor.Result();
        r.title = TITLE;
        r.kind = app != null ? app.toUpperCase() : "ÉCRAN";
        for (Item it : items) r.paragraphs.add(it.text);
        Library.Entry e = Library.add(this, r, SOURCE);
        Library.savePosition(this, e.id, start, 0);
        reader.playFrom(e.id, start);
    }

    private String currentAppLabel() {
        try {
            AccessibilityNodeInfo root = appRoot();
            if (root == null || root.getPackageName() == null) return null;
            PackageManager pm = getPackageManager();
            CharSequence l = pm.getApplicationLabel(pm.getApplicationInfo(root.getPackageName().toString(), 0));
            return l == null ? null : l.toString();
        } catch (Exception e) {
            return null;
        }
    }

    /** Fenêtre de l'appli affichée (pas la barre d'état, ni le clavier, ni notre bulle). */
    private AccessibilityNodeInfo appRoot() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root != null && !getPackageName().contentEquals(root.getPackageName() == null ? "" : root.getPackageName())) {
            return root;
        }
        try {
            for (AccessibilityWindowInfo w : getWindows()) {
                if (w.getType() != AccessibilityWindowInfo.TYPE_APPLICATION) continue;
                AccessibilityNodeInfo r = w.getRoot();
                if (r != null && r.getPackageName() != null && !getPackageName().contentEquals(r.getPackageName())) return r;
            }
        } catch (Exception ignored) {
        }
        return root;
    }

    /** Récupère les textes de l'écran dans l'ordre de lecture. */
    List<Item> collect() {
        List<Item> out = new ArrayList<Item>();
        AccessibilityNodeInfo root = appRoot();
        if (root == null) return out;
        walk(root, out, 0);
        return out;
    }

    private void walk(AccessibilityNodeInfo n, List<Item> out, int depth) {
        if (n == null || depth > 80 || out.size() > 4000) return;
        if (n.isPassword()) return;
        CharSequence t = n.getText();
        boolean skipText = n.isEditable() && !n.isMultiLine(); // barre d'adresse, champs de recherche
        String text = null;
        if (!skipText && t != null && t.length() > 0) {
            text = t.toString();
        } else if (n.getChildCount() == 0 && !n.isClickable() && n.getContentDescription() != null) {
            // Image avec une description (illustration d'un article…).
            text = n.getContentDescription().toString();
        }
        if (text != null) {
            text = text.replace(' ', ' ').replaceAll("\\s+", " ").trim();
            boolean hasLetter = false;
            for (int i = 0; i < text.length() && !hasLetter; i++) hasLetter = Character.isLetterOrDigit(text.charAt(i));
            if (hasLetter && (out.isEmpty() || !out.get(out.size() - 1).text.equals(text))) {
                Rect b = new Rect();
                n.getBoundsInScreen(b);
                out.add(new Item(text, b, n.isVisibleToUser()));
            }
        }
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo c = n.getChild(i);
            if (c != null) walk(c, out, depth + 1);
        }
    }

    // ------------------------------------------------------------------ toucher pour lire

    private void startTouchMode() {
        snapshot = collect();
        snapshotApp = currentAppLabel();
        if (snapshot.isEmpty()) {
            Toast.makeText(this, "Aucun texte à lire sur cet écran.", Toast.LENGTH_SHORT).show();
            return;
        }
        if (reader != null && reader.isPlaying()) reader.pause();
        touchLayer = new FrameLayout(this);
        touchLayer.setBackgroundColor(0x30000000);
        TextView hint = new TextView(this);
        hint.setText("Touche le texte à partir duquel lire");
        hint.setTextColor(0xFFFFFFFF);
        hint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        hint.setTypeface(Typeface.DEFAULT_BOLD);
        int p = Ui.dp(this, 14);
        hint.setPadding(p, p, p, p);
        hint.setBackground(Ui.rounded(Ui.BRAND, Ui.dp(this, 14)));
        FrameLayout.LayoutParams hl = new FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.TOP | Gravity.CENTER_HORIZONTAL);
        hl.topMargin = Ui.dp(this, 60);
        touchLayer.addView(hint, hl);
        final long shownAt = SystemClock.uptimeMillis();
        touchLayer.setOnTouchListener(new View.OnTouchListener() {
            @Override public boolean onTouch(View v, MotionEvent e) {
                if (e.getActionMasked() == MotionEvent.ACTION_UP && SystemClock.uptimeMillis() - shownAt > 300) {
                    int x = (int) e.getRawX(), y = (int) e.getRawY();
                    hideTouchLayer();
                    readAt(x, y);
                }
                return true;
            }
        });
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        try {
            wm.addView(touchLayer, lp);
        } catch (Exception e) {
            touchLayer = null;
            return;
        }
        // Sans toucher dans les 8 secondes : on annule.
        main.postDelayed(new Runnable() {
            @Override public void run() {
                if (touchLayer != null && SystemClock.uptimeMillis() - shownAt >= 7900) hideTouchLayer();
            }
        }, 8000);
    }

    private void hideTouchLayer() {
        if (touchLayer != null) {
            try { wm.removeView(touchLayer); } catch (Exception ignored) {}
            touchLayer = null;
        }
    }

    private void readAt(int x, int y) {
        if (snapshot == null || snapshot.isEmpty() || reader == null) return;
        int best = -1;
        long bestArea = Long.MAX_VALUE;
        for (int i = 0; i < snapshot.size(); i++) {
            Item it = snapshot.get(i);
            if (!it.visible || !it.bounds.contains(x, y)) continue;
            long area = (long) it.bounds.width() * it.bounds.height();
            if (area < bestArea) { bestArea = area; best = i; }
        }
        if (best < 0) {
            // Touché entre deux textes : on prend le premier texte visible en dessous.
            for (int i = 0; i < snapshot.size(); i++) {
                Item it = snapshot.get(i);
                if (it.visible && it.bounds.top >= y) { best = i; break; }
            }
        }
        if (best < 0) {
            Toast.makeText(this, "Pas de texte à cet endroit.", Toast.LENGTH_SHORT).show();
            return;
        }
        play(snapshot, best, snapshotApp);
        snapshot = null;
    }

    // ------------------------------------------------------------------ rappels du lecteur

    @Override public void onPosition(int para, int sentence) {}
    @Override public void onWord(int para, int start, int end) {}
    @Override public void onState(boolean playing) { setBubblePlaying(playing && isScreenDoc()); }
    @Override public void onTtsReady(boolean ok, String error) {
        if (!ok && error != null && !TextUtils.isEmpty(error)) Toast.makeText(this, error, Toast.LENGTH_LONG).show();
    }
    @Override public void onFinished() { setBubblePlaying(false); }
    @Override public void onDocumentChanged() {}
}
