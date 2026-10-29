package com.echomatras.lisys;

import android.accessibilityservice.AccessibilityButtonController;
import android.accessibilityservice.AccessibilityService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.Parcelable;
import android.os.SystemClock;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.util.DisplayMetrics;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.HapticFeedbackConstants;
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
 * Bouton flottant « Lisys » par-dessus toutes les applis.
 * - Appui : lit le texte affiché (site web, appli, message…). Nouvel appui : arrêt.
 * - Appui long : mode « lecture au doigt » : on glisse le doigt sur le texte,
 *   Lisys lit la phrase sous le doigt et l'entoure en jaune.
 */
public class ScreenReaderService extends AccessibilityService implements ReaderService.Listener {

    static final String SOURCE = "ecran";
    static final String TITLE = "Lecture de l'écran";
    private static final long FINGER_IDLE_MS = 90000;

    /** Un bloc de texte vu à l'écran, avec sa position. */
    static final class Item {
        final String text;          // texte nettoyé (celui qui est lu)
        final int[] map;            // position dans le texte d'origine -> position dans le texte nettoyé
        final Rect bounds;
        final boolean visible;
        final AccessibilityNodeInfo node;
        RectF[] chars;              // position de chaque caractère à l'écran, si l'appli la fournit
        boolean charsTried;
        boolean fromDescription;    // texte venant d'une description et non du texte affiché

        Item(String t, int[] m, Rect b, boolean v, AccessibilityNodeInfo n) {
            text = t; map = m; bounds = b; visible = v; node = n;
        }
    }

    private final Handler main = new Handler(Looper.getMainLooper());
    private WindowManager wm;
    private TextView bubble;
    private WindowManager.LayoutParams bubbleLp;
    private ReaderService reader;
    private boolean bound;
    private AccessibilityButtonController.AccessibilityButtonCallback buttonCallback;

    // Mode lecture au doigt
    private FrameLayout fingerRoot;
    private FingerLayer fingerLayer;
    private List<Item> fingerItems;
    private String fingerDocId;
    private int lastPara = -1, lastSent = -1;
    private long lastTouch;

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
                    if ("bubble".equals(key) || "bubbleSize".equals(key) || "bubbleColor".equals(key)) {
                        hideBubble();
                        if (Prefs.bubble(ScreenReaderService.this)) showBubble();
                    } else if ("volumeKeys".equals(key)) {
                        applyKeyFilter();
                    } else if (key != null && key.startsWith("caption")) {
                        hideCaption(); // recréé avec les nouveaux réglages à la prochaine phrase
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
        applyKeyFilter();
        // Bouton d'accessibilité d'Android (barre de navigation ou geste) : même action que la bulle.
        try {
            buttonCallback = new AccessibilityButtonController.AccessibilityButtonCallback() {
                @Override public void onClicked(AccessibilityButtonController c) { onBubbleTap(); }
            };
            getAccessibilityButtonController().registerAccessibilityButtonCallback(buttonCallback, main);
        } catch (Exception ignored) {
        }
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // On ne lit l'écran que quand on appuie sur le bouton ; seules les notifications de messages
        // sont suivies, et seulement si l'option « Annoncer les messages » est activée.
        if (event.getEventType() == AccessibilityEvent.TYPE_NOTIFICATION_STATE_CHANGED) onNotification(event);
    }

    @Override
    public void onInterrupt() {
        if (reader != null && isScreenDoc()) reader.pause();
    }

    @Override
    public void onDestroy() {
        getSharedPreferences("reglages", MODE_PRIVATE).unregisterOnSharedPreferenceChangeListener(prefsListener);
        stopFingerMode(false);
        hideCaption();
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

    private int[] bubbleColors() {
        int i = Prefs.bubbleColor(this);
        if (i < 0 || i >= Ui.BUBBLE_COLORS.length) i = 0;
        return Ui.BUBBLE_COLORS[i];
    }

    private void showBubble() {
        if (bubble != null || wm == null) return;
        int sizeDp = Prefs.bubbleSize(this);
        int size = Ui.dp(this, sizeDp);
        int[] col = bubbleColors();
        bubble = new TextView(this);
        bubble.setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeDp * 0.40f);
        bubble.setGravity(Gravity.CENTER);
        bubble.setTypeface(Typeface.DEFAULT_BOLD);
        bubble.setTextColor(col[1]);
        GradientDrawable d = new GradientDrawable();
        d.setShape(GradientDrawable.OVAL);
        d.setColor(col[0]);
        // Double bordure (couleur + contour opposé) : la bulle se voit sur fond clair comme sur fond sombre.
        d.setStroke(Math.max(Ui.dp(this, 3), size / 18), col[2]);
        bubble.setBackground(d);
        bubble.setElevation(Ui.dp(this, 8));
        bubble.setAccessibilityDelegate(new View.AccessibilityDelegate() {
            @Override public void onInitializeAccessibilityNodeInfo(View host, AccessibilityNodeInfo info) {
                super.onInitializeAccessibilityNodeInfo(host, info);
                info.addAction(new AccessibilityNodeInfo.AccessibilityAction(AccessibilityNodeInfo.ACTION_CLICK,
                        fingerRoot != null ? "Quitter la lecture au doigt" : "Lire l'écran"));
                info.addAction(new AccessibilityNodeInfo.AccessibilityAction(R.id.action_finger, "Lecture au doigt"));
            }
            @Override public boolean performAccessibilityAction(View host, int action, Bundle args) {
                if (action == R.id.action_finger) { startFingerMode(); return true; }
                if (action == AccessibilityNodeInfo.ACTION_CLICK) { onBubbleTap(); return true; }
                return super.performAccessibilityAction(host, action, args);
            }
        });
        updateBubbleState();

        DisplayMetrics dm = getResources().getDisplayMetrics();
        bubbleLp = new WindowManager.LayoutParams(size, size,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        bubbleLp.gravity = Gravity.TOP | Gravity.START;
        int x = Prefs.bubbleX(this), y = Prefs.bubbleY(this);
        int margin = Ui.dp(this, 6);
        if (x < 0) x = dm.widthPixels - size - margin;
        else if (x + size / 2 >= dm.widthPixels / 2) x = dm.widthPixels - size - margin; // garde le bon bord si la taille change
        else x = margin;
        bubbleLp.x = x;
        bubbleLp.y = y >= 0 ? Math.min(y, dm.heightPixels - size - margin) : dm.heightPixels / 2;
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

    /** Remet la bulle au-dessus de la couche du mode doigt, pour pouvoir quitter. */
    private void bringBubbleToFront() {
        if (bubble == null) return;
        try {
            wm.removeView(bubble);
            wm.addView(bubble, bubbleLp);
        } catch (Exception ignored) {
        }
    }

    private void updateBubbleState() {
        if (bubble == null) return;
        boolean playing = reader != null && reader.isPlaying() && isScreenDoc();
        if (fingerRoot != null) {
            bubble.setText("✋");
            bubble.setContentDescription("Lisys, lecture au doigt en cours. Touche pour quitter.");
        } else if (playing) {
            bubble.setText("⏹");
            bubble.setContentDescription("Lisys, lecture en cours. Touche pour arrêter.");
        } else {
            bubble.setText("🔊");
            bubble.setContentDescription("Lisys : lire l'écran. Appui long : lecture au doigt.");
        }
    }

    /** Appui = lire / arrêter, appui long = lecture au doigt, glisser = déplacer la bulle. */
    private final class BubbleTouch implements View.OnTouchListener {
        private float downX, downY;
        private int startX, startY;
        private boolean dragging, longDone;
        private final int slop = ViewConfiguration.get(ScreenReaderService.this).getScaledTouchSlop() * 2;
        private final Runnable longPress = new Runnable() {
            @Override public void run() {
                longDone = true;
                bubble.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS);
                if (fingerRoot == null) startFingerMode();
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
                    main.postDelayed(longPress, 600);
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
                        bubble.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
                        onBubbleTap();
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
        int margin = Ui.dp(this, 6);
        bubbleLp.x = bubbleLp.x + size / 2 < dm.widthPixels / 2 ? margin : dm.widthPixels - size - margin;
        bubbleLp.y = Math.min(bubbleLp.y, dm.heightPixels - size - margin);
        try { wm.updateViewLayout(bubble, bubbleLp); } catch (Exception ignored) {}
    }

    private void onBubbleTap() {
        if (fingerRoot != null) {
            stopFingerMode(true);
            return;
        }
        readScreen();
    }

    /** Petite annonce vocale (« Lecture au doigt »…) pour savoir ce qui se passe sans voir l'écran. */
    private void announce(String text) {
        if (!Prefs.bubbleVoice(this) || reader == null || !reader.isTtsReady() || reader.isPlaying()) return;
        try {
            reader.tts().speak(text, TextToSpeech.QUEUE_FLUSH, null, "annonce");
        } catch (Exception ignored) {
        }
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
        final String app = currentAppLabel();
        collectAsync(new ItemsCallback() {
            @Override public void done(List<Item> items) {
                if (reader == null) return;
                if (items.isEmpty()) {
                    Toast.makeText(ScreenReaderService.this, "Aucun texte à lire sur cet écran.", Toast.LENGTH_SHORT).show();
                    announce("Aucun texte à lire.");
                    return;
                }
                // On commence au premier texte visible ; la suite (bas d'une page, fin du mail) est lue ensuite.
                int start = 0;
                for (int i = 0; i < items.size(); i++) {
                    if (items.get(i).visible) { start = i; break; }
                }
                String id = saveDoc(items, app, start);
                reader.playFrom(id, start);
            }
        });
    }

    private String saveDoc(List<Item> items, String app, int start) {
        Extractor.Result r = new Extractor.Result();
        r.title = TITLE;
        r.kind = app != null ? app.toUpperCase() : "ÉCRAN";
        for (Item it : items) r.paragraphs.add(it.text);
        Library.Entry e = Library.add(this, r, SOURCE);
        Library.savePosition(this, e.id, start, 0);
        return e.id;
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
        if (root != null && root.getPackageName() != null && !getPackageName().contentEquals(root.getPackageName())) {
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

    /** Nombre de mini-navigateurs (WebView) vus à la dernière lecture, et texte trouvé dedans. */
    private int lastWebViews, lastWebChars, lastVisited;

    interface ItemsCallback { void done(List<Item> items); }

    /**
     * Lit l'écran, en réessayant quelques fois si une page web ou un mail (WebView) répond vide :
     * Chrome met son arbre d'accessibilité en veille et le reconstruit au premier appel.
     */
    private void collectAsync(final ItemsCallback cb) {
        attempt(0, null, cb);
    }

    private void attempt(final int n, List<Item> best, final ItemsCallback cb) {
        List<Item> items = collect();
        final List<Item> keep = best == null || totalChars(items) > totalChars(best) ? items : best;
        if (lastWebViews > 0 && lastWebChars < 80 && n < 5) {
            if (n == 0) announce("Un instant.");
            main.postDelayed(new Runnable() {
                @Override public void run() { attempt(n + 1, keep, cb); }
            }, 450);
            return;
        }
        saveReport(n, keep);
        cb.done(keep);
    }

    /** Rapport de la dernière lecture (sans le contenu complet), pour le dépannage. */
    private void saveReport(int attempts, List<Item> items) {
        StringBuilder sb = new StringBuilder();
        AccessibilityNodeInfo root = appRoot();
        sb.append("Lisys ").append(versionName()).append(" · Android ").append(android.os.Build.VERSION.RELEASE).append('\n');
        sb.append("Appli : ").append(root != null ? root.getPackageName() : "?").append('\n');
        sb.append("Éléments visités : ").append(lastVisited).append(" · textes : ").append(items.size())
                .append(" · caractères : ").append(totalChars(items)).append('\n');
        sb.append("WebView : ").append(lastWebViews).append(" · texte dans les WebView : ").append(lastWebChars)
                .append(" · essais : ").append(attempts + 1).append('\n');
        int shown = 0;
        for (Item it : items) {
            if (shown++ >= 12) break;
            String t = it.text.length() > 40 ? it.text.substring(0, 40) + "…" : it.text;
            sb.append(it.visible ? "• " : "◦ ").append(it.fromDescription ? "[desc] " : "").append(t).append('\n');
        }
        getSharedPreferences("reglages", MODE_PRIVATE).edit().putString("rapport", sb.toString()).apply();
    }

    private String versionName() {
        try { return getPackageManager().getPackageInfo(getPackageName(), 0).versionName; } catch (Exception e) { return "?"; }
    }

    private static int totalChars(List<Item> l) {
        int n = 0;
        for (Item it : l) n += it.text.length();
        return n;
    }

    /** Récupère les textes de l'écran dans l'ordre de lecture. */
    List<Item> collect() {
        List<Item> out = new ArrayList<Item>();
        lastWebViews = 0;
        lastWebChars = 0;
        AccessibilityNodeInfo root = appRoot();
        if (root == null) return out;
        // Parcours sans récursion : les mails mis en forme sont faits de tableaux imbriqués très profonds.
        ArrayList<AccessibilityNodeInfo> stack = new ArrayList<AccessibilityNodeInfo>();
        ArrayList<Boolean> inWeb = new ArrayList<Boolean>();
        stack.add(root);
        inWeb.add(false);
        int visited = 0;
        while (!stack.isEmpty() && visited < 20000 && out.size() < 6000) {
            AccessibilityNodeInfo n = stack.remove(stack.size() - 1);
            boolean web = inWeb.remove(inWeb.size() - 1);
            visited++;
            if (n == null || n.isPassword()) continue;
            CharSequence cls = n.getClassName();
            if (cls != null && cls.toString().contains("WebView")) {
                if (!web) lastWebViews++;
                web = true;
            }
            Item it = itemFor(n);
            if (it != null && (out.isEmpty() || !out.get(out.size() - 1).text.equals(it.text))) {
                out.add(it);
                if (web) lastWebChars += it.text.length();
            }
            for (int i = n.getChildCount() - 1; i >= 0; i--) {
                AccessibilityNodeInfo c = n.getChild(i);
                if (c != null) { stack.add(c); inWeb.add(web); }
            }
        }
        lastVisited = visited;
        return removeSummaries(out);
    }

    private Item itemFor(AccessibilityNodeInfo n) {
        CharSequence t = n.getText();
        boolean skipText = n.isEditable() && !n.isMultiLine(); // barre d'adresse, champs de recherche
        String raw = null;
        boolean fromText = false;
        if (!skipText && t != null && t.toString().trim().length() > 0) {
            raw = t.toString();
            fromText = true;
        } else if (n.getContentDescription() != null && (!n.isClickable() || n.getChildCount() > 0)) {
            // Texte fourni seulement comme description (certaines applis mail, images d'un article…).
            // Les simples boutons-icônes (« Retour », « Plus d'options ») sont ignorés.
            raw = n.getContentDescription().toString();
        }
        if (raw == null) return null;
        int[] map = new int[raw.length() + 1];
        String text = clean(raw, map);
        boolean hasLetter = false;
        for (int i = 0; i < text.length() && !hasLetter; i++) hasLetter = Character.isLetterOrDigit(text.charAt(i));
        if (!hasLetter) return null;
        Rect b = new Rect();
        n.getBoundsInScreen(b);
        Item it = new Item(text, map, b, n.isVisibleToUser(), fromText ? n : null);
        it.fromDescription = !fromText;
        return it;
    }

    /**
     * Une description qui résume ce qu'elle contient (ligne de la liste des mails : « De Paul, objet… »)
     * ferait lire deux fois la même chose : on la retire si les textes qu'elle contient suivent.
     */
    private static List<Item> removeSummaries(List<Item> in) {
        List<Item> out = new ArrayList<Item>();
        for (int i = 0; i < in.size(); i++) {
            Item it = in.get(i);
            if (it.fromDescription && i + 1 < in.size()) {
                Item next = in.get(i + 1);
                if (!next.fromDescription && it.bounds.contains(next.bounds) && it.text.contains(next.text)) continue;
            }
            out.add(it);
        }
        return out;
    }

    /** Regroupe les espaces, en gardant la correspondance des positions avec le texte d'origine. */
    static String clean(String raw, int[] map) {
        StringBuilder sb = new StringBuilder(raw.length());
        boolean pendingSpace = false;
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            if (Character.isWhitespace(c) || c == ' ') {
                pendingSpace = sb.length() > 0;
                map[i] = sb.length();
                continue;
            }
            if (pendingSpace) { sb.append(' '); pendingSpace = false; }
            map[i] = sb.length();
            sb.append(c);
        }
        map[raw.length()] = sb.length();
        return sb.toString();
    }

    // ------------------------------------------------------------------ lecture au doigt

    private void startFingerMode() {
        if (reader == null || fingerRoot != null) return;
        final String app = currentAppLabel();
        collectAsync(new ItemsCallback() {
            @Override public void done(List<Item> items) { startFingerMode(items, app); }
        });
    }

    private void startFingerMode(List<Item> items, String app) {
        if (reader == null || fingerRoot != null) return;
        fingerItems = items;
        if (fingerItems.isEmpty()) {
            Toast.makeText(this, "Aucun texte à lire sur cet écran.", Toast.LENGTH_SHORT).show();
            announce("Aucun texte à lire.");
            return;
        }
        if (reader.isPlaying()) reader.pause();
        int start = 0;
        for (int i = 0; i < fingerItems.size(); i++) if (fingerItems.get(i).visible) { start = i; break; }
        fingerDocId = saveDoc(fingerItems, app, start);
        reader.load(fingerDocId, true);
        lastPara = lastSent = -1;
        lastTouch = SystemClock.uptimeMillis();

        fingerRoot = new FrameLayout(this);
        fingerLayer = new FingerLayer(this);
        fingerRoot.addView(fingerLayer, new FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        final TextView hint = new TextView(this);
        hint.setText("✋ Glisse ton doigt sur le texte\nDeux doigts pour faire défiler\nTouche la bulle pour quitter");
        hint.setTextColor(0xFF000000);
        hint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20);
        hint.setTypeface(Typeface.DEFAULT_BOLD);
        hint.setGravity(Gravity.CENTER);
        int p = Ui.dp(this, 14);
        hint.setPadding(p, p, p, p);
        GradientDrawable hb = Ui.rounded(0xFFFFD600, Ui.dp(this, 16));
        hb.setStroke(Ui.dp(this, 3), 0xFF000000);
        hint.setBackground(hb);
        FrameLayout.LayoutParams hl = new FrameLayout.LayoutParams(FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        hl.bottomMargin = Ui.dp(this, 90);
        fingerRoot.addView(hint, hl);
        // Le message disparaît dès qu'on touche l'écran, ou au bout de 5 secondes.
        main.postDelayed(new Runnable() { @Override public void run() { hint.setVisibility(View.GONE); } }, 5000);
        fingerRoot.setOnTouchListener(new View.OnTouchListener() {
            @Override public boolean onTouch(View v, MotionEvent e) {
                hint.setVisibility(View.GONE);
                lastTouch = SystemClock.uptimeMillis();
                if (handleTwoFingers(e)) return true;
                int a = e.getActionMasked();
                if (a == MotionEvent.ACTION_DOWN || a == MotionEvent.ACTION_MOVE) {
                    lastTouch = SystemClock.uptimeMillis();
                    fingerAt((int) e.getRawX(), (int) e.getRawY());
                }
                return true;
            }
        });
        WindowManager.LayoutParams lp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT, WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                        | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        try {
            wm.addView(fingerRoot, lp);
        } catch (Exception e) {
            fingerRoot = null;
            return;
        }
        bringBubbleToFront();
        updateBubbleState();
        announce("Lecture au doigt. Glisse ton doigt sur le texte.");
        main.postDelayed(idleCheck, 5000);
    }

    private final Runnable idleCheck = new Runnable() {
        @Override public void run() {
            if (fingerRoot == null) return;
            boolean playing = reader != null && reader.isPlaying();
            if (!playing && SystemClock.uptimeMillis() - lastTouch > FINGER_IDLE_MS) {
                stopFingerMode(true);
                return;
            }
            main.postDelayed(this, 5000);
        }
    };

    private void stopFingerMode(boolean speak) {
        main.removeCallbacks(idleCheck);
        if (fingerRoot == null) return;
        try { wm.removeView(fingerRoot); } catch (Exception ignored) {}
        fingerRoot = null;
        fingerLayer = null;
        fingerItems = null;
        if (reader != null && reader.isPlaying() && isScreenDoc()) reader.pause();
        updateBubbleState();
        if (speak) announce("Fin de la lecture au doigt.");
    }

    /** Le doigt est à (x, y) : on lit la phrase qui est dessous, si ce n'est pas déjà celle en cours. */
    private void fingerAt(int x, int y) {
        if (fingerItems == null || reader == null) return;
        int idx = itemAt(x, y);
        if (idx < 0) return;
        Item it = fingerItems.get(idx);
        int clean = cleanIndexAt(it, x, y);
        List<int[]> ss = reader.sentences(idx);
        int sent = 0;
        for (int k = 0; k < ss.size(); k++) if (clean >= ss.get(k)[0]) sent = k;
        if (idx == lastPara && sent == lastSent && reader.isPlaying()) return;
        lastPara = idx;
        lastSent = sent;
        if (!fingerDocId.equals(reader.docId())) reader.load(fingerDocId, true);
        reader.seek(idx, sent);
        if (!reader.isPlaying()) reader.play();
        highlight(idx, sent);
    }

    /** Le plus petit bloc de texte sous le doigt, sinon le plus proche (à moins de 30 dp). */
    private int itemAt(int x, int y) {
        int best = -1;
        long bestArea = Long.MAX_VALUE;
        for (int i = 0; i < fingerItems.size(); i++) {
            Item it = fingerItems.get(i);
            if (!it.visible || !it.bounds.contains(x, y)) continue;
            long area = (long) it.bounds.width() * it.bounds.height();
            if (area < bestArea) { bestArea = area; best = i; }
        }
        if (best >= 0) return best;
        int max = Ui.dp(this, 30);
        double bestDist = Double.MAX_VALUE;
        for (int i = 0; i < fingerItems.size(); i++) {
            Item it = fingerItems.get(i);
            if (!it.visible || it.bounds.isEmpty()) continue;
            int dx = x < it.bounds.left ? it.bounds.left - x : x > it.bounds.right ? x - it.bounds.right : 0;
            int dy = y < it.bounds.top ? it.bounds.top - y : y > it.bounds.bottom ? y - it.bounds.bottom : 0;
            double d = Math.hypot(dx, dy);
            if (d < bestDist && d <= max) { bestDist = d; best = i; }
        }
        return best;
    }

    /** Position (dans le texte lu) du caractère sous le doigt. */
    private int cleanIndexAt(Item it, int x, int y) {
        RectF[] chars = chars(it);
        if (chars != null) {
            int bestI = -1;
            float bestD = Float.MAX_VALUE;
            for (int i = 0; i < chars.length; i++) {
                RectF r = chars[i];
                if (r == null || r.isEmpty()) continue;
                if (r.contains(x, y)) { bestI = i; break; }
                // Même ligne : le caractère le plus proche horizontalement.
                if (y >= r.top && y <= r.bottom) {
                    float d = Math.min(Math.abs(x - r.left), Math.abs(x - r.right));
                    if (d < bestD) { bestD = d; bestI = i; }
                }
            }
            if (bestI >= 0) return it.map[Math.min(bestI, it.map.length - 1)];
        }
        // Pas de positions de caractères : estimation selon la hauteur dans le bloc.
        if (it.bounds.height() <= 0) return 0;
        float frac = Math.max(0f, Math.min(1f, (y - it.bounds.top) / (float) it.bounds.height()));
        return Math.round(frac * Math.max(0, it.text.length() - 1));
    }

    /** Demande à l'appli la position de chaque caractère (Chrome, la plupart des applis Android). */
    private RectF[] chars(Item it) {
        if (it.charsTried) return it.chars;
        it.charsTried = true;
        if (it.node == null) return null;
        try {
            List<String> extras = it.node.getAvailableExtraData();
            String key = AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_KEY;
            if (extras == null || !extras.contains(key)) return null;
            CharSequence t = it.node.getText();
            if (t == null) return null;
            Bundle args = new Bundle();
            args.putInt(AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_ARG_START_INDEX, 0);
            args.putInt(AccessibilityNodeInfo.EXTRA_DATA_TEXT_CHARACTER_LOCATION_ARG_LENGTH, Math.min(t.length(), 20000));
            if (!it.node.refreshWithExtraData(key, args)) return null;
            Parcelable[] arr = it.node.getExtras().getParcelableArray(key);
            if (arr == null) return null;
            RectF[] out = new RectF[arr.length];
            for (int i = 0; i < arr.length; i++) out[i] = arr[i] instanceof RectF ? (RectF) arr[i] : null;
            it.chars = out;
        } catch (Exception ignored) {
        }
        return it.chars;
    }

    /** Entoure en jaune la phrase lue (ligne par ligne si l'appli donne la position des caractères). */
    private void highlight(int idx, int sent) {
        if (fingerLayer == null || fingerItems == null || idx < 0 || idx >= fingerItems.size() || reader == null) return;
        Item it = fingerItems.get(idx);
        List<int[]> ss = reader.sentences(idx);
        List<RectF> rects = new ArrayList<RectF>();
        if (sent >= 0 && sent < ss.size()) {
            int s = ss.get(sent)[0], e = ss.get(sent)[1];
            RectF[] chars = chars(it);
            if (chars != null) {
                RectF line = null;
                for (int i = 0; i < chars.length && i < it.map.length - 1; i++) {
                    int c = it.map[i];
                    RectF r = chars[i];
                    if (c < s || c >= e || r == null || r.isEmpty()) continue;
                    if (line != null && Math.abs(r.centerY() - line.centerY()) < line.height() / 2) {
                        line.union(r);
                    } else {
                        if (line != null) rects.add(line);
                        line = new RectF(r);
                    }
                }
                if (line != null) rects.add(line);
            }
            if (rects.isEmpty()) {
                Rect b = it.bounds;
                int len = Math.max(1, it.text.length());
                float top = b.top + b.height() * (s / (float) len);
                float bottom = b.top + b.height() * (e / (float) len);
                if (ss.size() <= 1) { top = b.top; bottom = b.bottom; }
                rects.add(new RectF(b.left, top, b.right, Math.max(bottom, top + Ui.dp(this, 24))));
            }
        }
        fingerLayer.setRects(rects);
    }

    /** Couche transparente du mode doigt, qui dessine le cadre jaune. */
    private static final class FingerLayer extends View {
        private final Paint fill = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint stroke = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint outline = new Paint(Paint.ANTI_ALIAS_FLAG);
        private List<RectF> rects = new ArrayList<RectF>();
        private final int[] loc = new int[2];
        private final float pad, radius;

        FingerLayer(Context c) {
            super(c);
            fill.setColor(0x44FFEB3B);
            stroke.setColor(0xFFFFD600);
            stroke.setStyle(Paint.Style.STROKE);
            stroke.setStrokeWidth(Ui.dp(c, 4));
            outline.setColor(0xFF000000);
            outline.setStyle(Paint.Style.STROKE);
            outline.setStrokeWidth(Ui.dp(c, 7));
            pad = Ui.dp(c, 4);
            radius = Ui.dp(c, 6);
        }

        void setRects(List<RectF> r) {
            rects = r;
            invalidate();
        }

        @Override
        protected void onDraw(Canvas canvas) {
            canvas.drawColor(0x14000000); // léger voile : on sait que le mode doigt est actif
            getLocationOnScreen(loc);
            for (RectF r0 : rects) {
                RectF r = new RectF(r0.left - loc[0] - pad, r0.top - loc[1] - pad, r0.right - loc[0] + pad, r0.bottom - loc[1] + pad);
                canvas.drawRoundRect(r, radius, radius, fill);
                canvas.drawRoundRect(r, radius, radius, outline);
                canvas.drawRoundRect(r, radius, radius, stroke);
            }
        }
    }

    // ------------------------------------------------------------------ bandeau en très gros texte (option)

    private TextView caption;
    private WindowManager.LayoutParams captionLp;
    private final Runnable hideCaptionTask = new Runnable() {
        @Override public void run() { hideCaption(); }
    };

    /** Le bandeau s'affiche quand Lisys lit hors de son écran de lecture (bulle, arrière-plan). */
    private boolean captionWanted() {
        return Prefs.caption(this) && reader != null && reader.isPlaying()
                && (isScreenDoc() || !ReaderActivity.visible);
    }

    private void updateCaption(int para, int sent, int wordStart, int wordEnd) {
        if (!captionWanted()) {
            if (caption != null && (reader == null || !reader.isPlaying())) {
                main.removeCallbacks(hideCaptionTask);
                main.postDelayed(hideCaptionTask, 1500);
            } else if (caption != null && !Prefs.caption(this)) {
                hideCaption();
            }
            return;
        }
        main.removeCallbacks(hideCaptionTask);
        List<String> paras = reader.paragraphs();
        if (para < 0 || para >= paras.size()) return;
        List<int[]> ss = reader.sentences(para);
        if (sent < 0 || sent >= ss.size()) return;
        int[] b = ss.get(sent);
        String p = paras.get(para);
        String sentence = p.substring(b[0], b[1]);
        int lead = sentence.length() - sentence.replaceAll("^\\s+", "").length();
        sentence = sentence.trim();
        if (caption == null) showCaption();
        if (caption == null) return;
        int[] col = Ui.CAPTION_COLORS[Math.max(0, Math.min(Prefs.captionColors(this), Ui.CAPTION_COLORS.length - 1))];
        android.text.SpannableString s = new android.text.SpannableString(sentence);
        int ws = wordStart - b[0] - lead, we = wordEnd - b[0] - lead;
        if (wordStart >= 0 && ws >= 0 && we <= sentence.length() && we > ws) {
            s.setSpan(new android.text.style.BackgroundColorSpan(col[2]), ws, we, 0);
            s.setSpan(new android.text.style.ForegroundColorSpan(col[3]), ws, we, 0);
        }
        caption.setText(s);
        // Garde le mot lu visible si la phrase dépasse la hauteur du bandeau.
        final int target = Math.max(0, ws);
        caption.post(new Runnable() {
            @Override public void run() {
                if (caption == null || caption.getLayout() == null) return;
                android.text.Layout l = caption.getLayout();
                int line = l.getLineForOffset(Math.min(target, Math.max(0, caption.length() - 1)));
                int y = l.getLineTop(line);
                int h = caption.getHeight() - caption.getPaddingTop() - caption.getPaddingBottom();
                int scroll = caption.getScrollY();
                if (y < scroll || l.getLineBottom(line) > scroll + h) caption.scrollTo(0, Math.max(0, y - h / 3));
                else if (target == 0) caption.scrollTo(0, 0);
            }
        });
    }

    private void showCaption() {
        if (wm == null) return;
        int[] col = Ui.CAPTION_COLORS[Math.max(0, Math.min(Prefs.captionColors(this), Ui.CAPTION_COLORS.length - 1))];
        caption = new TextView(this);
        caption.setTextSize(TypedValue.COMPLEX_UNIT_SP, Prefs.captionSize(this));
        caption.setTypeface(Typeface.DEFAULT_BOLD);
        caption.setTextColor(col[1]);
        caption.setLineSpacing(0, 1.1f);
        int p = Ui.dp(this, 16);
        caption.setPadding(p, p, p, p);
        GradientDrawable d = Ui.rounded(col[0], Ui.dp(this, 14));
        d.setStroke(Ui.dp(this, 3), col[1]);
        caption.setBackground(d);
        caption.setMaxHeight(getResources().getDisplayMetrics().heightPixels * 2 / 5);
        caption.setVerticalScrollBarEnabled(false);
        caption.setMovementMethod(new android.text.method.ScrollingMovementMethod());
        captionLp = new WindowManager.LayoutParams(WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.WRAP_CONTENT,
                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
                        | WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                PixelFormat.TRANSLUCENT);
        captionLp.gravity = (Prefs.captionTop(this) ? Gravity.TOP : Gravity.BOTTOM) | Gravity.CENTER_HORIZONTAL;
        captionLp.x = 0;
        captionLp.y = Prefs.captionTop(this) ? Ui.dp(this, 32) : Ui.dp(this, 56);
        caption.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        try {
            wm.addView(caption, captionLp);
        } catch (Exception e) {
            caption = null;
            return;
        }
        if (bubble != null) bringBubbleToFront();
    }

    private void hideCaption() {
        main.removeCallbacks(hideCaptionTask);
        if (caption != null) {
            try { wm.removeView(caption); } catch (Exception ignored) {}
            caption = null;
        }
    }

    // ------------------------------------------------------------------ boutons de volume (option)

    private long volDownAt;
    private boolean volLongDone;
    private boolean volSinglePending;
    private final Runnable volLong = new Runnable() {
        @Override public void run() {
            volLongDone = true;
            if (fingerRoot != null) stopFingerMode(true);
            else startFingerMode();
        }
    };
    private final Runnable volSingle = new Runnable() {
        @Override public void run() {
            // Un seul appui : c'était vraiment pour baisser le son.
            volSinglePending = false;
            android.media.AudioManager am = (android.media.AudioManager) getSystemService(AUDIO_SERVICE);
            am.adjustSuggestedStreamVolume(android.media.AudioManager.ADJUST_LOWER,
                    android.media.AudioManager.USE_DEFAULT_STREAM_TYPE, android.media.AudioManager.FLAG_SHOW_UI);
        }
    };

    /** Active ou non la réception des touches, selon l'option (sinon Android ne nous les envoie pas). */
    private void applyKeyFilter() {
        try {
            android.accessibilityservice.AccessibilityServiceInfo info = getServiceInfo();
            if (info == null) return;
            int f = android.accessibilityservice.AccessibilityServiceInfo.FLAG_REQUEST_FILTER_KEY_EVENTS;
            if (Prefs.volumeKeys(this)) info.flags |= f;
            else info.flags &= ~f;
            setServiceInfo(info);
        } catch (Exception ignored) {
        }
    }

    @Override
    protected boolean onKeyEvent(android.view.KeyEvent e) {
        if (!Prefs.volumeKeys(this) || e.getKeyCode() != android.view.KeyEvent.KEYCODE_VOLUME_DOWN) return false;
        android.media.AudioManager am = (android.media.AudioManager) getSystemService(AUDIO_SERVICE);
        if (am.getMode() != android.media.AudioManager.MODE_NORMAL) return false; // appel en cours : on ne touche à rien
        if (e.getAction() == android.view.KeyEvent.ACTION_DOWN) {
            if (e.getRepeatCount() == 0) {
                volDownAt = SystemClock.uptimeMillis();
                volLongDone = false;
                main.postDelayed(volLong, 800);
            }
            return true;
        }
        if (e.getAction() == android.view.KeyEvent.ACTION_UP) {
            main.removeCallbacks(volLong);
            if (volLongDone) return true;
            if (volSinglePending) {
                // Double appui : lire l'écran (ou arrêter / quitter le mode doigt).
                main.removeCallbacks(volSingle);
                volSinglePending = false;
                onBubbleTap();
            } else {
                volSinglePending = true;
                main.postDelayed(volSingle, 400);
            }
            return true;
        }
        return false;
    }

    // ------------------------------------------------------------------ annonce des messages (option)

    private static final String[] MESSAGING_APPS = {
            "com.whatsapp", "com.whatsapp.w4b", "com.facebook.orca", "org.telegram.messenger",
            "org.thoughtcrime.securesms", "com.google.android.apps.messaging", "com.samsung.android.messaging",
            "com.android.mms", "com.google.android.gm", "com.microsoft.office.outlook",
            "com.samsung.android.email.provider", "com.android.email", "com.instagram.android",
            "com.snapchat.android", "com.viber.voip", "com.skype.raider", "com.discord"};
    private String lastAnnounceKey;
    private long lastAnnounceAt;

    private void onNotification(AccessibilityEvent event) {
        if (!Prefs.announce(this) || reader == null || !reader.isTtsReady()) return;
        Parcelable data = event.getParcelableData();
        if (!(data instanceof android.app.Notification)) return;
        android.app.Notification n = (android.app.Notification) data;
        String pkg = event.getPackageName() == null ? "" : event.getPackageName().toString();
        if (pkg.equals(getPackageName())) return;
        if ((n.flags & android.app.Notification.FLAG_GROUP_SUMMARY) != 0) return;
        if ((n.flags & android.app.Notification.FLAG_ONGOING_EVENT) != 0) return;
        boolean messaging = android.app.Notification.CATEGORY_MESSAGE.equals(n.category)
                || android.app.Notification.CATEGORY_EMAIL.equals(n.category)
                || (n.extras != null && n.extras.containsKey(android.app.Notification.EXTRA_MESSAGES));
        for (String m : MESSAGING_APPS) if (m.equals(pkg)) messaging = true;
        if (!messaging) return;
        // Pas pendant un appel, ni en mode Ne pas déranger, ni pendant une lecture.
        android.media.AudioManager am = (android.media.AudioManager) getSystemService(AUDIO_SERVICE);
        if (am.getMode() != android.media.AudioManager.MODE_NORMAL) return;
        android.app.NotificationManager nm = (android.app.NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm.getCurrentInterruptionFilter() > android.app.NotificationManager.INTERRUPTION_FILTER_ALL) return;
        if (reader.isPlaying()) return;

        CharSequence title = n.extras == null ? null : n.extras.getCharSequence(android.app.Notification.EXTRA_TITLE);
        CharSequence text = n.extras == null ? null : n.extras.getCharSequence(android.app.Notification.EXTRA_TEXT);
        if (n.extras != null) {
            Parcelable[] msgs = n.extras.getParcelableArray(android.app.Notification.EXTRA_MESSAGES);
            if (msgs != null && msgs.length > 0 && msgs[msgs.length - 1] instanceof Bundle) {
                Bundle last = (Bundle) msgs[msgs.length - 1];
                CharSequence t = last.getCharSequence("text");
                if (t != null) text = t;
                CharSequence who = last.getCharSequence("sender");
                if (who != null && who.length() > 0) title = who;
            }
        }
        if (title == null && text == null) return;
        String key = pkg + "|" + title + "|" + text;
        long now = SystemClock.uptimeMillis();
        if (key.equals(lastAnnounceKey) && now - lastAnnounceAt < 30000) return;
        lastAnnounceKey = key;
        lastAnnounceAt = now;
        String app = appLabel(pkg);
        StringBuilder sb = new StringBuilder("Nouveau message");
        if (title != null && title.length() > 0) sb.append(" de ").append(title);
        if (app != null) sb.append(", ").append(app);
        if (Prefs.announceContent(this) && text != null && text.length() > 0) {
            String t = text.toString().replaceAll("\\s+", " ").trim();
            if (t.length() > 300) t = t.substring(0, 300) + "…";
            sb.append(". ").append(t);
        }
        try {
            reader.tts().speak(sb.toString(), TextToSpeech.QUEUE_ADD, null, "annonce");
        } catch (Exception ignored) {
        }
    }

    private String appLabel(String pkg) {
        try {
            PackageManager pm = getPackageManager();
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (Exception e) {
            return null;
        }
    }

    // ------------------------------------------------------------------ défilement à deux doigts (mode doigt)

    private float twoFingerY = Float.NaN;
    private boolean twoFingers;

    /** Renvoie true si l'événement a été traité comme un geste à deux doigts. */
    private boolean handleTwoFingers(MotionEvent e) {
        int a = e.getActionMasked();
        if (a == MotionEvent.ACTION_DOWN) { twoFingers = false; twoFingerY = Float.NaN; return false; }
        if (e.getPointerCount() >= 2) {
            float y = (e.getY(0) + e.getY(1)) / 2f;
            if (!twoFingers || Float.isNaN(twoFingerY)) {
                twoFingers = true;
                twoFingerY = y;
                return true;
            }
            float dy = y - twoFingerY;
            if (Math.abs(dy) > Ui.dp(this, 80)) {
                twoFingerY = y;
                scrollScreen(dy < 0);
            }
            return true;
        }
        if (a == MotionEvent.ACTION_UP) { boolean was = twoFingers; twoFingers = false; twoFingerY = Float.NaN; return was; }
        return twoFingers; // un doigt levé sur deux : on attend que tout soit relâché
    }

    /** Fait défiler la page sous le texte (doigts vers le haut = page suivante), puis relit l'écran. */
    private void scrollScreen(boolean forward) {
        AccessibilityNodeInfo target = null;
        if (fingerItems != null && lastPara >= 0 && lastPara < fingerItems.size()) {
            AccessibilityNodeInfo n = fingerItems.get(lastPara).node;
            while (n != null && target == null) {
                if (n.isScrollable()) target = n;
                else n = n.getParent();
            }
        }
        if (target == null) target = findScrollable(appRoot(), 0);
        if (target == null) {
            announce("Rien à faire défiler.");
            return;
        }
        if (reader != null && reader.isPlaying()) reader.pause();
        boolean ok = target.performAction(forward ? AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                : AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD);
        if (fingerRoot != null) fingerRoot.performHapticFeedback(HapticFeedbackConstants.VIRTUAL_KEY);
        if (!ok) {
            announce(forward ? "Fin de la page." : "Début de la page.");
            return;
        }
        if (fingerLayer != null) fingerLayer.setRects(new ArrayList<RectF>());
        // Après le défilement, on relit ce qui est affiché pour suivre le nouveau texte.
        main.postDelayed(new Runnable() {
            @Override public void run() {
                if (fingerRoot == null) return;
                final String app = currentAppLabel();
                collectAsync(new ItemsCallback() {
                    @Override public void done(List<Item> items) {
                        if (fingerRoot == null || items.isEmpty()) return;
                        fingerItems = items;
                        fingerDocId = saveDoc(items, app, 0);
                        reader.load(fingerDocId, true);
                        lastPara = lastSent = -1;
                    }
                });
            }
        }, 600);
    }

    private AccessibilityNodeInfo findScrollable(AccessibilityNodeInfo n, int depth) {
        if (n == null || depth > 60) return null;
        if (n.isScrollable() && n.isVisibleToUser()) return n;
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo r = findScrollable(n.getChild(i), depth + 1);
            if (r != null) return r;
        }
        return null;
    }

    // ------------------------------------------------------------------ rappels du lecteur

    @Override public void onPosition(int para, int sentence) {
        updateCaption(para, sentence, -1, -1);
        // En mode doigt, le cadre jaune suit la lecture quand elle continue après la phrase touchée.
        if (fingerRoot != null && isScreenDoc()) highlight(para, sentence);
    }
    @Override public void onWord(int para, int start, int end) {
        if (reader != null && caption != null) updateCaption(para, reader.sentence(), start, end);
    }
    @Override public void onState(boolean playing) {
        updateBubbleState();
        if (reader != null) updateCaption(reader.para(), reader.sentence(), -1, -1);
    }
    @Override public void onTtsReady(boolean ok, String error) {
        if (!ok && error != null) Toast.makeText(this, error, Toast.LENGTH_LONG).show();
    }
    @Override public void onFinished() { updateBubbleState(); hideCaption(); }
    @Override public void onDocumentChanged() {}
}
