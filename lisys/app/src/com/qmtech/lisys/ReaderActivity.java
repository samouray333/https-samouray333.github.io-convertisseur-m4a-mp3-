package com.qmtech.lisys;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ComponentName;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.media.AudioManager;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import android.text.Layout;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.TextUtils;
import android.text.style.BackgroundColorSpan;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.AbsListView;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Écran de lecture : texte surligné phrase par phrase et mot par mot, commandes de lecture. */
public class ReaderActivity extends Activity implements ReaderService.Listener {

    public static final String EXTRA_ID = "id";
    public static final String EXTRA_AUTOPLAY = "autoplay";
    /** Écran de lecture affiché (le bandeau flottant est alors inutile). */
    static volatile boolean visible;
    private static final int REQ_STORAGE = 5;

    private String docId;
    private boolean autoplay;
    private ReaderService svc;
    private Ui.Palette pal;

    private List<String> paras = new ArrayList<String>();
    private int curPara = -1, curSent = -1, wordStart = -1, wordEnd = -1;
    private float textSize;
    private boolean bigMode;
    private long userScrollAt;
    private float touchX, touchY;
    private int searchFrom;
    private String lastSearch = "";

    private TextView titleView, playBtn, progressText, speedChip, sleepChip, bigText;
    private ListView list;
    private ScrollView bigPanel;
    private SeekBar seek;
    private ParaAdapter adapter;
    private boolean seeking;

    private final ServiceConnection conn = new ServiceConnection() {
        @Override public void onServiceConnected(ComponentName n, IBinder b) {
            svc = ((ReaderService.LocalBinder) b).service();
            svc.load(docId);
            paras = svc.paragraphs();
            curPara = svc.para();
            curSent = svc.sentence();
            adapter.notifyDataSetChanged();
            seek.setMax(Math.max(0, paras.size() - 1));
            svc.addListener(ReaderActivity.this);
            onState(svc.isPlaying());
            updateProgress();
            jumpTo(curPara);
            updateBig();
            if (autoplay) {
                autoplay = false;
                getIntent().putExtra(EXTRA_AUTOPLAY, false);
                svc.play();
            }
        }

        @Override public void onServiceDisconnected(ComponentName n) { svc = null; }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setVolumeControlStream(AudioManager.STREAM_MUSIC);
        readIntent(getIntent());
        if (state != null) autoplay = false;
        build();
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        String old = docId;
        readIntent(intent);
        if (svc != null && !docId.equals(old)) {
            svc.load(docId);
            paras = svc.paragraphs();
            curPara = svc.para();
            curSent = svc.sentence();
            Library.Entry e = Library.get(this, docId);
            titleView.setText(e != null ? e.title : "");
            seek.setMax(Math.max(0, paras.size() - 1));
            adapter.notifyDataSetChanged();
            jumpTo(curPara);
            updateProgress();
            updateBig();
            if (autoplay) { autoplay = false; svc.play(); }
        }
    }

    private void readIntent(Intent i) {
        docId = i.getStringExtra(EXTRA_ID);
        autoplay = i.getBooleanExtra(EXTRA_AUTOPLAY, false);
        if (docId == null) {
            List<Library.Entry> l = Library.list(this);
            if (l.isEmpty()) { finish(); docId = ""; return; }
            docId = l.get(0).id;
        }
        Library.touch(this, docId);
    }

    @Override
    protected void onResume() {
        super.onResume();
        visible = true;
    }

    @Override
    protected void onPause() {
        visible = false;
        super.onPause();
    }

    @Override
    protected void onStart() {
        super.onStart();
        bindService(new Intent(this, ReaderService.class), conn, Context.BIND_AUTO_CREATE);
    }

    @Override
    protected void onStop() {
        if (svc != null) svc.removeListener(this);
        try { unbindService(conn); } catch (Exception ignored) {}
        svc = null;
        super.onStop();
    }

    // ------------------------------------------------------------------ interface

    private void build() {
        pal = Ui.palette(this);
        Ui.systemBars(this, pal);
        textSize = Prefs.textSize(this);
        bigMode = Prefs.bigMode(this);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);

        // Barre du haut
        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setBackgroundColor(pal.bar);
        int p8 = Ui.dp(this, 8);
        top.setPadding(p8, p8, p8, p8);
        TextView back = Ui.roundButton(this, "←", "Retour", pal.bar, pal.barText, 46);
        back.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { finish(); } });
        top.addView(back);
        Library.Entry e = Library.get(this, docId);
        titleView = Ui.label(this, e != null ? e.title : "", 17, pal.barText, true);
        titleView.setSingleLine(true);
        titleView.setEllipsize(TextUtils.TruncateAt.END);
        top.addView(titleView, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        TextView smaller = Ui.roundButton(this, "A−", "Texte plus petit", pal.bar, pal.barText, 46);
        smaller.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { zoom(-2); } });
        top.addView(smaller);
        TextView bigger = Ui.roundButton(this, "A+", "Texte plus grand", pal.bar, pal.barText, 46);
        bigger.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { zoom(2); } });
        top.addView(bigger);
        TextView loupe = Ui.roundButton(this, "🔍", "Mode grand texte", pal.bar, pal.barText, 46);
        loupe.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { toggleBig(); } });
        top.addView(loupe);
        TextView menu = Ui.roundButton(this, "⋮", "Plus d'options", pal.bar, pal.barText, 46);
        menu.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showMenu(); } });
        top.addView(menu);
        root.addView(top);

        // Texte
        list = new ListView(this);
        list.setDivider(null);
        list.setSelector(android.R.color.transparent);
        list.setCacheColorHint(pal.bg);
        list.setPadding(0, Ui.dp(this, 6), 0, Ui.dp(this, 120));
        list.setClipToPadding(false);
        adapter = new ParaAdapter();
        list.setAdapter(adapter);
        list.setOnScrollListener(new AbsListView.OnScrollListener() {
            @Override public void onScrollStateChanged(AbsListView v, int s) {
                if (s == SCROLL_STATE_TOUCH_SCROLL || s == SCROLL_STATE_FLING) userScrollAt = SystemClock.elapsedRealtime();
            }
            @Override public void onScroll(AbsListView v, int a, int b, int c) {}
        });
        list.setOnItemClickListener(new AdapterView.OnItemClickListener() {
            @Override public void onItemClick(AdapterView<?> a, View v, int pos, long id) { tapParagraph(pos, (TextView) v); }
        });
        list.setOnItemLongClickListener(new AdapterView.OnItemLongClickListener() {
            @Override public boolean onItemLongClick(AdapterView<?> a, View v, int pos, long id) {
                paragraphMenu(pos);
                return true;
            }
        });

        bigPanel = new ScrollView(this);
        bigPanel.setFillViewport(true);
        bigText = new TextView(this);
        bigText.setTextColor(pal.text);
        bigText.setGravity(Gravity.CENTER_VERTICAL);
        int p20 = Ui.dp(this, 20);
        bigText.setPadding(p20, p20, p20, p20);
        bigText.setLineSpacing(0, 1.15f);
        bigPanel.addView(bigText, new ScrollView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        LinearLayout.LayoutParams fill = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1);
        root.addView(list, fill);
        root.addView(bigPanel, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        // Commandes
        LinearLayout bottom = new LinearLayout(this);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setBackgroundColor(pal.bar);
        bottom.setPadding(Ui.dp(this, 12), Ui.dp(this, 6), Ui.dp(this, 12), Ui.dp(this, 10));

        progressText = Ui.label(this, "", 13, pal.muted, false);
        progressText.setGravity(Gravity.CENTER);
        bottom.addView(progressText, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        seek = new SeekBar(this);
        seek.setContentDescription("Position dans le document");
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int v, boolean user) {
                if (user) progressText.setText("Aller au paragraphe " + (v + 1) + " / " + paras.size());
            }
            @Override public void onStartTrackingTouch(SeekBar s) { seeking = true; }
            @Override public void onStopTrackingTouch(SeekBar s) {
                seeking = false;
                if (svc != null) svc.seek(s.getProgress(), 0);
                userScrollAt = 0;
                jumpTo(s.getProgress());
            }
        });
        bottom.addView(seek);

        LinearLayout controls = new LinearLayout(this);
        controls.setOrientation(LinearLayout.HORIZONTAL);
        controls.setGravity(Gravity.CENTER);
        TextView prevPara = Ui.roundButton(this, "⏮", "Paragraphe précédent", pal.surface, pal.text, 50);
        TextView prev = Ui.roundButton(this, "◀", "Phrase précédente", pal.surface, pal.text, 56);
        playBtn = Ui.roundButton(this, "▶", "Lire", pal.button, pal.buttonText, 74);
        TextView next = Ui.roundButton(this, "▶▶", "Phrase suivante", pal.surface, pal.text, 56);
        next.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        TextView nextPara = Ui.roundButton(this, "⏭", "Paragraphe suivant", pal.surface, pal.text, 50);
        prevPara.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (svc != null) { userScrollAt = 0; svc.previousParagraph(); } } });
        prev.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (svc != null) { userScrollAt = 0; svc.previous(); } } });
        playBtn.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (svc != null) { userScrollAt = 0; svc.toggle(); } } });
        next.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (svc != null) { userScrollAt = 0; svc.next(); } } });
        nextPara.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { if (svc != null) { userScrollAt = 0; svc.nextParagraph(); } } });
        controls.addView(prevPara);
        controls.addView(prev);
        controls.addView(playBtn);
        controls.addView(next);
        controls.addView(nextPara);
        bottom.addView(controls);

        LinearLayout chips = new LinearLayout(this);
        chips.setOrientation(LinearLayout.HORIZONTAL);
        chips.setGravity(Gravity.CENTER);
        chips.setPadding(0, Ui.dp(this, 8), 0, 0);
        speedChip = chip("Vitesse " + speedLabel(Prefs.rate(this)));
        speedChip.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { speedDialog(); } });
        TextView voiceChip = chip("Voix");
        voiceChip.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { voiceDialog(); } });
        sleepChip = chip("Minuterie");
        sleepChip.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { sleepDialog(); } });
        chips.addView(speedChip);
        chips.addView(voiceChip);
        chips.addView(sleepChip);
        bottom.addView(chips);

        root.addView(bottom);
        Ui.setContent(this, root);
        applyBigMode();
    }

    private TextView chip(String text) {
        TextView t = Ui.label(this, text, 15, pal.text, true);
        t.setGravity(Gravity.CENTER);
        int h = Ui.dp(this, 14), v = Ui.dp(this, 8);
        t.setPadding(h, v, h, v);
        Ui.background(t, pal.surface, Ui.dp(this, 20), 0x33888888);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(Ui.dp(this, 4), 0, Ui.dp(this, 4), 0);
        t.setLayoutParams(lp);
        t.setClickable(true);
        return t;
    }

    private static String speedLabel(float r) {
        return String.format(Locale.FRANCE, "%.1f×", r);
    }

    private final class ParaAdapter extends BaseAdapter {
        @Override public int getCount() { return paras.size(); }
        @Override public Object getItem(int i) { return paras.get(i); }
        @Override public long getItemId(int i) { return i; }

        @Override
        public View getView(int i, View convert, ViewGroup parent) {
            TextView t = (TextView) convert;
            if (t == null) {
                t = new TextView(ReaderActivity.this);
                int h = Ui.dp(ReaderActivity.this, 18), v = Ui.dp(ReaderActivity.this, 10);
                t.setPadding(h, v, h, v);
                t.setLineSpacing(0, 1.25f);
                t.setOnTouchListener(new View.OnTouchListener() {
                    @Override public boolean onTouch(View view, MotionEvent ev) {
                        if (ev.getAction() == MotionEvent.ACTION_DOWN) { touchX = ev.getX(); touchY = ev.getY(); }
                        return false;
                    }
                });
            }
            t.setTextSize(TypedValue.COMPLEX_UNIT_SP, textSize);
            t.setTextColor(pal.text);
            bindPara(t, i);
            return t;
        }
    }

    private void bindPara(TextView t, int i) {
        String p = paras.get(i);
        // Le titre (premier paragraphe des pages web) un peu plus visible.
        boolean heading = p.length() < 90 && !p.endsWith(".") && i == 0;
        t.setTypeface(heading ? Typeface.DEFAULT_BOLD : Typeface.DEFAULT);
        if (i != curPara) {
            t.setText(p);
            t.setBackgroundColor(pal.bg);
            return;
        }
        t.setBackgroundColor(pal.paraBg);
        SpannableString s = new SpannableString(p);
        if (svc != null) {
            List<int[]> ss = svc.sentences(i);
            if (curSent >= 0 && curSent < ss.size()) {
                int[] b = ss.get(curSent);
                s.setSpan(new BackgroundColorSpan(pal.sentBg), b[0], b[1], Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                if (pal.dark && Prefs.theme(this) == Prefs.THEME_CONTRASTE) {
                    s.setSpan(new ForegroundColorSpan(0xFFFFFFFF), b[0], b[1], Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                }
            }
        }
        if (Prefs.followWord(this) && wordStart >= 0 && wordEnd <= p.length() && wordEnd > wordStart) {
            s.setSpan(new BackgroundColorSpan(pal.wordBg), wordStart, wordEnd, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            s.setSpan(new ForegroundColorSpan(pal.wordText), wordStart, wordEnd, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        t.setText(s);
    }

    private TextView viewFor(int para) {
        int first = list.getFirstVisiblePosition();
        View v = list.getChildAt(para - first);
        return v instanceof TextView ? (TextView) v : null;
    }

    private void refreshPara(int para) {
        if (para < 0 || para >= paras.size()) return;
        TextView t = viewFor(para);
        if (t != null) bindPara(t, para);
    }

    /** Garde la phrase lue visible, sauf si l'utilisateur fait défiler le texte lui-même. */
    private void ensureVisible() {
        if (bigMode || curPara < 0) return;
        if (SystemClock.elapsedRealtime() - userScrollAt < 5000) return;
        TextView t = viewFor(curPara);
        int h = list.getHeight();
        if (t == null) {
            list.setSelectionFromTop(curPara, h / 5);
            return;
        }
        Layout layout = t.getLayout();
        int y = t.getTop();
        if (layout != null && svc != null) {
            List<int[]> ss = svc.sentences(curPara);
            int off = wordStart >= 0 ? wordStart : (curSent >= 0 && curSent < ss.size() ? ss.get(curSent)[0] : 0);
            int line = layout.getLineForOffset(Math.min(off, Math.max(0, paras.get(curPara).length() - 1)));
            y += t.getPaddingTop() + layout.getLineTop(line);
        }
        if (y < h / 10 || y > h * 2 / 3) list.smoothScrollBy(y - h / 5, 350);
    }

    private void jumpTo(int para) {
        if (para >= 0 && para < paras.size()) list.setSelectionFromTop(para, list.getHeight() / 5);
    }

    private void tapParagraph(int pos, TextView v) {
        if (svc == null) return;
        int sentence = 0;
        try {
            int off = v.getOffsetForPosition(touchX, touchY);
            List<int[]> ss = svc.sentences(pos);
            for (int k = 0; k < ss.size(); k++) if (off >= ss.get(k)[0]) sentence = k;
        } catch (Exception ignored) {
        }
        userScrollAt = 0;
        svc.seek(pos, sentence);
        if (!svc.isPlaying()) svc.play();
    }

    private void paragraphMenu(final int pos) {
        new AlertDialog.Builder(this)
                .setItems(new String[]{"Lire à partir d'ici", "Copier ce paragraphe", "Partager ce paragraphe"},
                        new DialogInterface.OnClickListener() {
                            @Override public void onClick(DialogInterface d, int w) {
                                String text = paras.get(pos);
                                if (w == 0 && svc != null) { svc.seek(pos, 0); if (!svc.isPlaying()) svc.play(); }
                                else if (w == 1) {
                                    android.content.ClipboardManager cm = (android.content.ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
                                    cm.setPrimaryClip(android.content.ClipData.newPlainText("Lisys", text));
                                    Toast.makeText(ReaderActivity.this, "Copié", Toast.LENGTH_SHORT).show();
                                } else shareText(text);
                            }
                        })
                .show();
    }

    private void zoom(int delta) {
        textSize = Math.max(14, Math.min(60, textSize + delta));
        Prefs.setTextSize(this, textSize);
        adapter.notifyDataSetChanged();
        updateBig();
        Toast.makeText(this, "Taille du texte : " + Math.round(textSize), Toast.LENGTH_SHORT).show();
    }

    private void toggleBig() {
        bigMode = !bigMode;
        Prefs.setBigMode(this, bigMode);
        applyBigMode();
        if (!bigMode) { userScrollAt = 0; jumpTo(curPara); }
        Toast.makeText(this, bigMode ? "Mode grand texte : la phrase lue s'affiche en très grand"
                : "Mode page", Toast.LENGTH_SHORT).show();
    }

    private void applyBigMode() {
        list.setVisibility(bigMode ? View.GONE : View.VISIBLE);
        bigPanel.setVisibility(bigMode ? View.VISIBLE : View.GONE);
        updateBig();
    }

    /** Mode grand texte (style loupe) : seule la phrase en cours, en très gros caractères. */
    private void updateBig() {
        if (!bigMode || bigText == null) return;
        bigText.setTextSize(TypedValue.COMPLEX_UNIT_SP, Math.min(96, textSize * 1.9f));
        if (svc == null || curPara < 0 || curPara >= paras.size()) { bigText.setText(""); return; }
        List<int[]> ss = svc.sentences(curPara);
        if (curSent < 0 || curSent >= ss.size()) { bigText.setText(""); return; }
        int[] b = ss.get(curSent);
        String p = paras.get(curPara);
        String sentence = p.substring(b[0], b[1]).trim();
        int lead = p.substring(b[0], b[1]).indexOf(sentence.length() > 0 ? sentence.charAt(0) : ' ');
        SpannableString s = new SpannableString(sentence);
        int ws = wordStart - b[0] - Math.max(0, lead), we = wordEnd - b[0] - Math.max(0, lead);
        if (Prefs.followWord(this) && wordStart >= 0 && ws >= 0 && we <= sentence.length() && we > ws) {
            s.setSpan(new BackgroundColorSpan(pal.wordBg), ws, we, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            s.setSpan(new ForegroundColorSpan(pal.wordText), ws, we, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            s.setSpan(new StyleSpan(Typeface.BOLD), ws, we, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        bigText.setText(s);
        // Fait défiler jusqu'au mot lu si la phrase dépasse l'écran.
        final int target = Math.max(0, ws);
        bigText.post(new Runnable() {
            @Override public void run() {
                Layout l = bigText.getLayout();
                if (l == null) return;
                int y = l.getLineTop(l.getLineForOffset(Math.min(target, Math.max(0, bigText.length() - 1))));
                int h = bigPanel.getHeight();
                if (y + bigText.getPaddingTop() > bigPanel.getScrollY() + h * 2 / 3 || y < bigPanel.getScrollY()) {
                    bigPanel.smoothScrollTo(0, Math.max(0, y - h / 4));
                }
            }
        });
    }

    private void updateProgress() {
        if (seeking || paras.isEmpty()) return;
        int pct = paras.size() <= 1 ? 0 : Math.round(100f * curPara / (paras.size() - 1));
        progressText.setText("Paragraphe " + (curPara + 1) + " / " + paras.size() + "  ·  " + pct + " %");
        seek.setProgress(Math.max(0, curPara));
        long sleep = svc != null ? svc.sleepRemainingMs() : 0;
        sleepChip.setText(sleep > 0 ? "Arrêt dans " + Math.max(1, (sleep + 59999) / 60000) + " min" : "Minuterie");
    }

    // ------------------------------------------------------------------ rappels du service

    @Override
    public void onPosition(int para, int sentence) {
        int old = curPara;
        curPara = para;
        curSent = sentence;
        wordStart = wordEnd = -1;
        if (old != para) refreshPara(old);
        refreshPara(para);
        updateProgress();
        updateBig();
        ensureVisible();
    }

    @Override
    public void onWord(int para, int start, int end) {
        if (para != curPara) return;
        wordStart = start;
        wordEnd = end;
        if (!Prefs.followWord(this)) return;
        refreshPara(para);
        updateBig();
        ensureVisible();
    }

    @Override
    public void onState(boolean playing) {
        playBtn.setText(playing ? "❚❚" : "▶");
        playBtn.setContentDescription(playing ? "Pause" : "Lire");
        if (!playing) {
            wordStart = wordEnd = -1;
            refreshPara(curPara);
            updateBig();
        }
        updateProgress();
    }

    @Override
    public void onTtsReady(boolean ok, String error) {
        if (!ok && error != null) {
            new AlertDialog.Builder(this).setTitle("Synthèse vocale").setMessage(error)
                    .setPositiveButton("Installer", new DialogInterface.OnClickListener() {
                        @Override public void onClick(DialogInterface d, int w) { MainActivity.installVoices(ReaderActivity.this); }
                    })
                    .setNegativeButton("Fermer", null).show();
        }
    }

    @Override
    public void onDocumentChanged() {
        if (svc == null) return;
        docId = svc.docId();
        paras = svc.paragraphs();
        curPara = svc.para();
        curSent = svc.sentence();
        wordStart = wordEnd = -1;
        Library.Entry e = Library.get(this, docId);
        titleView.setText(e != null ? e.title : "");
        seek.setMax(Math.max(0, paras.size() - 1));
        adapter.notifyDataSetChanged();
        jumpTo(curPara);
        updateProgress();
        updateBig();
    }

    @Override
    public void onFinished() {
        Toast.makeText(this, "Fin du document", Toast.LENGTH_SHORT).show();
    }

    // ------------------------------------------------------------------ menus

    private void showMenu() {
        final List<String> items = new ArrayList<String>();
        items.add("Rechercher dans le texte");
        items.add("Créer un fichier audio (.m4a)");
        items.add("Thème : " + Ui.themeName(Prefs.theme(this)));
        items.add((Prefs.followWord(this) ? "✓ " : "") + "Surligner le mot lu");
        items.add((bigMode ? "✓ " : "") + "Mode grand texte (loupe)");
        items.add("Revenir au début");
        items.add("Partager tout le texte");
        new AlertDialog.Builder(this)
                .setItems(items.toArray(new String[0]), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        switch (w) {
                            case 0: searchDialog(); break;
                            case 1: exportAudio(); break;
                            case 2: MainActivity.chooseTheme(ReaderActivity.this, new Runnable() {
                                @Override public void run() { rebuild(); }
                            }); break;
                            case 3:
                                Prefs.setFollowWord(ReaderActivity.this, !Prefs.followWord(ReaderActivity.this));
                                refreshPara(curPara);
                                updateBig();
                                break;
                            case 4: toggleBig(); break;
                            case 5: if (svc != null) { userScrollAt = 0; svc.seek(0, 0); jumpTo(0); } break;
                            default:
                                StringBuilder sb = new StringBuilder();
                                for (String p : paras) sb.append(p).append("\n\n");
                                shareText(sb.toString());
                        }
                    }
                })
                .show();
    }

    private void rebuild() {
        build();
        if (svc != null) {
            paras = svc.paragraphs();
            seek.setMax(Math.max(0, paras.size() - 1));
            onState(svc.isPlaying());
        }
        adapter.notifyDataSetChanged();
        updateProgress();
        jumpTo(curPara);
    }

    private void shareText(String text) {
        if (text.length() > 90000) text = text.substring(0, 90000);
        Intent i = new Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text);
        startActivity(Intent.createChooser(i, "Partager le texte"));
    }

    private void speedDialog() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        int p = Ui.dp(this, 22);
        box.setPadding(p, p, p, 0);
        final TextView rateLabel = new TextView(this);
        rateLabel.setTextSize(TypedValue.COMPLEX_UNIT_SP, 17);
        final SeekBar rate = new SeekBar(this);
        rate.setMax(25); // 0,5× à 3,0× par pas de 0,1
        rate.setProgress(Math.round((Prefs.rate(this) - 0.5f) * 10));
        final TextView pitchLabel = new TextView(this);
        pitchLabel.setTextSize(TypedValue.COMPLEX_UNIT_SP, 17);
        pitchLabel.setPadding(0, Ui.dp(this, 16), 0, 0);
        final SeekBar pitch = new SeekBar(this);
        pitch.setMax(15); // 0,5 à 2,0
        pitch.setProgress(Math.round((Prefs.pitch(this) - 0.5f) * 10));
        SeekBar.OnSeekBarChangeListener l = new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar s, int v, boolean u) {
                rateLabel.setText("Vitesse : " + speedLabel(0.5f + rate.getProgress() / 10f));
                pitchLabel.setText("Tonalité : " + String.format(Locale.FRANCE, "%.1f", 0.5f + pitch.getProgress() / 10f));
            }
            @Override public void onStartTrackingTouch(SeekBar s) {}
            @Override public void onStopTrackingTouch(SeekBar s) {
                if (svc == null) return;
                if (s == rate) {
                    float r = 0.5f + rate.getProgress() / 10f;
                    svc.setRate(r);
                    speedChip.setText("Vitesse " + speedLabel(r));
                } else {
                    svc.setPitch(0.5f + pitch.getProgress() / 10f);
                }
            }
        };
        rate.setOnSeekBarChangeListener(l);
        pitch.setOnSeekBarChangeListener(l);
        l.onProgressChanged(rate, 0, false);
        box.addView(rateLabel);
        box.addView(rate);
        box.addView(pitchLabel);
        box.addView(pitch);
        new AlertDialog.Builder(this).setTitle("Vitesse et tonalité").setView(box)
                .setNeutralButton("Par défaut", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        if (svc == null) return;
                        svc.setRate(1f);
                        svc.setPitch(1f);
                        speedChip.setText("Vitesse " + speedLabel(1f));
                    }
                })
                .setPositiveButton("OK", null).show();
    }

    private void voiceDialog() {
        if (svc == null || !svc.isTtsReady()) {
            Toast.makeText(this, "La synthèse vocale démarre, réessaie dans un instant.", Toast.LENGTH_SHORT).show();
            return;
        }
        final List<Voice> voices = new ArrayList<Voice>();
        for (Voice v : svc.voices()) {
            Set<String> f = v.getFeatures();
            // Voix pas encore téléchargées : on les masque.
            if (f != null && f.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)) continue;
            voices.add(v);
        }
        final List<String> names = new ArrayList<String>();
        names.add("Voix par défaut (français)");
        String current = Prefs.voice(this);
        int checked = 0;
        int frCount = 0;
        for (int i = 0; i < voices.size(); i++) {
            Voice v = voices.get(i);
            String lang = v.getLocale().getDisplayName(Locale.FRENCH);
            lang = lang.length() > 0 ? Character.toUpperCase(lang.charAt(0)) + lang.substring(1) : v.getLocale().toString();
            StringBuilder sb = new StringBuilder(lang);
            if ("fr".equals(v.getLocale().getLanguage())) sb.append(" · voix ").append(++frCount);
            else sb.append(" · ").append(shortName(v.getName()));
            if (v.getQuality() >= Voice.QUALITY_HIGH) sb.append(" · haute qualité");
            sb.append(v.isNetworkConnectionRequired() ? " · en ligne" : " · hors ligne");
            names.add(sb.toString());
            if (v.getName().equals(current)) checked = i + 1;
        }
        new AlertDialog.Builder(this)
                .setTitle("Choisir la voix")
                .setSingleChoiceItems(names.toArray(new String[0]), checked, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        if (svc == null) return;
                        Voice v = w == 0 ? null : voices.get(w - 1);
                        svc.setVoice(v);
                        if (!svc.isPlaying()) {
                            boolean fr = v == null || "fr".equals(v.getLocale().getLanguage());
                            svc.tts().speak(fr ? "Bonjour, voici la voix choisie." : "Hello, this is the selected voice.",
                                    TextToSpeech.QUEUE_FLUSH, null, "apercu");
                        }
                    }
                })
                .setPositiveButton("OK", null)
                .setNeutralButton("Plus de voix", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { MainActivity.installVoices(ReaderActivity.this); }
                })
                .show();
    }

    private static String shortName(String n) {
        int i = n.lastIndexOf('-');
        return n.length() > 24 && i > 0 ? n.substring(0, 24) + "…" : n;
    }

    private void sleepDialog() {
        final int[] minutes = {0, 10, 15, 30, 45, 60, 90};
        String[] labels = {"Désactivée", "10 minutes", "15 minutes", "30 minutes", "45 minutes", "1 heure", "1 h 30"};
        new AlertDialog.Builder(this)
                .setTitle("Arrêter la lecture dans…")
                .setItems(labels, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        if (svc != null) svc.setSleepTimer(minutes[w]);
                        updateProgress();
                    }
                })
                .show();
    }

    private void searchDialog() {
        final EditText field = new EditText(this);
        field.setSingleLine(true);
        field.setHint("Mot ou expression");
        field.setText(lastSearch);
        LinearLayout box = new LinearLayout(this);
        int p = Ui.dp(this, 20);
        box.setPadding(p, Ui.dp(this, 8), p, 0);
        box.addView(field, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        new AlertDialog.Builder(this).setTitle("Rechercher").setView(box)
                .setPositiveButton("Suivant", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { search(field.getText().toString()); }
                })
                .setNegativeButton("Annuler", null).show();
    }

    private void search(String q) {
        q = q.trim();
        if (q.length() == 0 || paras.isEmpty()) return;
        if (!q.equalsIgnoreCase(lastSearch)) searchFrom = curPara + 1;
        lastSearch = q;
        String needle = q.toLowerCase(Locale.FRENCH);
        for (int k = 0; k < paras.size(); k++) {
            int i = (searchFrom + k) % paras.size();
            String p = paras.get(i).toLowerCase(Locale.FRENCH);
            int at = p.indexOf(needle);
            if (at >= 0) {
                searchFrom = i + 1;
                int sentence = 0;
                if (svc != null) {
                    List<int[]> ss = svc.sentences(i);
                    for (int s = 0; s < ss.size(); s++) if (at >= ss.get(s)[0]) sentence = s;
                    svc.seek(i, sentence);
                }
                userScrollAt = 0;
                jumpTo(i);
                Toast.makeText(this, "Trouvé au paragraphe " + (i + 1) + ". Appuie sur Lire.", Toast.LENGTH_SHORT).show();
                return;
            }
        }
        Toast.makeText(this, "« " + q + " » introuvable", Toast.LENGTH_SHORT).show();
    }

    private void exportAudio() {
        if (ExportService.isRunning()) {
            Toast.makeText(this, "Un export est déjà en cours (voir les notifications).", Toast.LENGTH_LONG).show();
            return;
        }
        if (Build.VERSION.SDK_INT < 29 && checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_STORAGE);
            return;
        }
        int chars = 0;
        for (String p : paras) chars += p.length();
        // Environ 900 caractères par minute à vitesse normale.
        int minutes = Math.max(1, Math.round(chars / (900f * Prefs.rate(this))));
        new AlertDialog.Builder(this)
                .setTitle("Créer un fichier audio")
                .setMessage("Le document entier va être enregistré en .m4a avec la voix et la vitesse actuelles "
                        + "(environ " + minutes + " min d'écoute).\n\nLe fichier sera dans Téléchargements/Lisys. "
                        + "La création continue en arrière-plan, tu peux suivre la progression dans les notifications.")
                .setPositiveButton("Créer", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        Intent i = new Intent(ReaderActivity.this, ExportService.class).putExtra(ExportService.EXTRA_ID, docId);
                        startForegroundService(i);
                    }
                })
                .setNegativeButton("Annuler", null).show();
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] perms, int[] res) {
        if (req == REQ_STORAGE && res.length > 0 && res[0] == PackageManager.PERMISSION_GRANTED) exportAudio();
    }

    @Override
    public boolean onKeyDown(int code, KeyEvent ev) {
        if (svc != null) {
            if (code == KeyEvent.KEYCODE_SPACE) { svc.toggle(); return true; }
            if (code == KeyEvent.KEYCODE_DPAD_RIGHT) { svc.next(); return true; }
            if (code == KeyEvent.KEYCODE_DPAD_LEFT) { svc.previous(); return true; }
        }
        return super.onKeyDown(code, ev);
    }
}
