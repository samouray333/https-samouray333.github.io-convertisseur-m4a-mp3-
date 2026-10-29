package com.echomatras.lisys;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.text.InputType;
import android.text.format.DateUtils;
import android.util.Patterns;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;

/** Écran d'accueil : ouvrir un document, une page web, du texte, ou reprendre une lecture. */
public class MainActivity extends Activity {

    private static final int REQ_OPEN = 1;
    private static final int REQ_NOTIF = 2;

    private final Handler main = new Handler(Looper.getMainLooper());
    private Ui.Palette pal;
    private ListView list;
    private TextView empty;
    private RecentAdapter adapter;
    private AlertDialog busy;
    private TextView busyText;
    private int themeShown = -1;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        build();
        askNotificationPermission();
        if (state == null) handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (themeShown != Prefs.theme(this)) build();
        refresh();
    }

    // ------------------------------------------------------------------ interface

    private void build() {
        themeShown = Prefs.theme(this);
        pal = Ui.palette(this);
        Ui.systemBars(this, pal);
        int pad = Ui.dp(this, 16);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(pal.bg);
        root.setPadding(pad, pad, pad, 0);

        LinearLayout head = new LinearLayout(this);
        head.setOrientation(LinearLayout.HORIZONTAL);
        head.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        TextView t = Ui.label(this, "Lisys", 32, pal.text, true);
        titles.addView(t);
        titles.addView(Ui.label(this, "Tes documents et pages web lus à voix haute", 15, pal.muted, false));
        head.addView(titles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        TextView gear = Ui.roundButton(this, "⚙", "Réglages", pal.surface, pal.text, 52);
        gear.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { showSettings(); }
        });
        head.addView(gear);
        root.addView(head);

        root.addView(space(14));
        Button open = Ui.bigButton(this, "📄   Ouvrir un document", pal.button, pal.buttonText);
        open.setContentDescription("Ouvrir un document : PDF, Word, livre EPUB, texte");
        open.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { pickDocument(); }
        });
        root.addView(open, fullWidth());
        root.addView(space(10));

        Button web = Ui.bigButton(this, "🌐   Lire une page web", pal.button, pal.buttonText);
        web.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { askUrl(); }
        });
        root.addView(web, fullWidth());
        root.addView(space(10));

        Button clip = Ui.bigButton(this, "📋   Lire le texte copié", pal.surface, pal.text);
        clip.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { readClipboard(); }
        });
        root.addView(clip, fullWidth());

        root.addView(space(20));
        root.addView(Ui.label(this, "Reprendre la lecture", 18, pal.text, true));
        root.addView(space(6));

        empty = Ui.label(this, "Aucun document pour l'instant.\n\nAstuce : dans n'importe quelle appli, "
                + "sélectionne du texte puis choisis « Lire avec Lisys ». Tu peux aussi partager une page "
                + "depuis Chrome ou un fichier depuis Mes fichiers vers Lisys.", 16, pal.muted, false);
        root.addView(empty);

        list = new ListView(this);
        list.setDivider(null);
        list.setDividerHeight(Ui.dp(this, 8));
        list.setClipToPadding(false);
        list.setPadding(0, 0, 0, pad);
        list.setSelector(android.R.color.transparent);
        adapter = new RecentAdapter();
        list.setAdapter(adapter);
        list.setOnItemClickListener(new AdapterView.OnItemClickListener() {
            @Override public void onItemClick(AdapterView<?> a, View v, int pos, long id) {
                openReader(adapter.items.get(pos).id, false);
            }
        });
        list.setOnItemLongClickListener(new AdapterView.OnItemLongClickListener() {
            @Override public boolean onItemLongClick(AdapterView<?> a, View v, int pos, long id) {
                confirmRemove(adapter.items.get(pos));
                return true;
            }
        });
        root.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
    }

    private View space(int dp) {
        View v = new View(this);
        v.setLayoutParams(new LinearLayout.LayoutParams(1, Ui.dp(this, dp)));
        return v;
    }

    private LinearLayout.LayoutParams fullWidth() {
        return new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
    }

    private void refresh() {
        adapter.items = Library.list(this);
        adapter.notifyDataSetChanged();
        empty.setVisibility(adapter.items.isEmpty() ? View.VISIBLE : View.GONE);
    }

    private final class RecentAdapter extends BaseAdapter {
        List<Library.Entry> items = new ArrayList<Library.Entry>();

        @Override public int getCount() { return items.size(); }
        @Override public Object getItem(int i) { return items.get(i); }
        @Override public long getItemId(int i) { return i; }

        @Override
        public View getView(int i, View convert, ViewGroup parent) {
            LinearLayout row;
            TextView title, meta;
            if (convert == null) {
                row = new LinearLayout(MainActivity.this);
                row.setOrientation(LinearLayout.VERTICAL);
                int p = Ui.dp(MainActivity.this, 14);
                row.setPadding(p, p, p, p);
                Ui.background(row, pal.surface, Ui.dp(MainActivity.this, 14), 0x22888888);
                title = Ui.label(MainActivity.this, "", 17, pal.text, true);
                title.setMaxLines(2);
                meta = Ui.label(MainActivity.this, "", 14, pal.muted, false);
                row.addView(title);
                row.addView(meta);
            } else {
                row = (LinearLayout) convert;
                title = (TextView) row.getChildAt(0);
                meta = (TextView) row.getChildAt(1);
            }
            Library.Entry e = items.get(i);
            title.setText(e.title);
            String when = DateUtils.getRelativeTimeSpanString(e.opened, System.currentTimeMillis(),
                    DateUtils.MINUTE_IN_MILLIS).toString();
            meta.setText(e.kind + "  ·  lu à " + e.percent() + " %  ·  " + when);
            row.setContentDescription(e.title + ", " + e.kind + ", lu à " + e.percent() + " pour cent");
            return row;
        }
    }

    private void confirmRemove(final Library.Entry e) {
        new AlertDialog.Builder(this)
                .setTitle(e.title)
                .setItems(new String[]{"Lire depuis le début", "Retirer de la liste"}, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int which) {
                        if (which == 0) {
                            Library.savePosition(MainActivity.this, e.id, 0, 0);
                            openReader(e.id, true);
                        } else {
                            Library.remove(MainActivity.this, e.id);
                            refresh();
                        }
                    }
                })
                .show();
    }

    // ------------------------------------------------------------------ actions

    private void pickDocument() {
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        i.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.oasis.opendocument.text",
                "application/epub+zip",
                "application/rtf", "text/rtf",
                "text/*", "application/xhtml+xml", "application/octet-stream"});
        try {
            startActivityForResult(i, REQ_OPEN);
        } catch (Exception e) {
            Toast.makeText(this, "Aucun gestionnaire de fichiers disponible.", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_OPEN && res == RESULT_OK && data != null && data.getData() != null) {
            importUri(data.getData());
        }
    }

    private void askUrl() {
        final EditText field = new EditText(this);
        field.setHint("https://…");
        field.setSingleLine(true);
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        field.setImeOptions(EditorInfo.IME_ACTION_GO);
        field.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18);
        String clip = clipboardText();
        String url = clip != null ? findUrl(clip) : null;
        field.setText(url != null ? url : Prefs.lastUrl(this));
        field.selectAll();
        LinearLayout box = new LinearLayout(this);
        int p = Ui.dp(this, 20);
        box.setPadding(p, Ui.dp(this, 8), p, 0);
        box.setOrientation(LinearLayout.VERTICAL);
        box.addView(field);
        TextView help = new TextView(this);
        help.setText("« Lire » récupère le texte de l'article directement. Si la page demande une connexion "
                + "ou ne s'affiche pas bien, choisis « Navigateur ».");
        help.setPadding(0, Ui.dp(this, 8), 0, 0);
        box.addView(help);
        final AlertDialog d = new AlertDialog.Builder(this)
                .setTitle("Lire une page web")
                .setView(box)
                .setPositiveButton("Lire", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface di, int w) { importUrl(field.getText().toString()); }
                })
                .setNeutralButton("Navigateur", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface di, int w) {
                        String u = field.getText().toString().trim();
                        Intent i = new Intent(MainActivity.this, WebActivity.class);
                        if (u.length() > 0) i.putExtra(WebActivity.EXTRA_URL, u);
                        startActivity(i);
                    }
                })
                .setNegativeButton("Annuler", null)
                .create();
        field.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override public boolean onEditorAction(TextView v, int action, android.view.KeyEvent ev) {
                d.dismiss();
                importUrl(field.getText().toString());
                return true;
            }
        });
        d.show();
    }

    private void readClipboard() {
        String text = clipboardText();
        if (text == null || text.trim().length() == 0) {
            askText();
            return;
        }
        String url = findUrl(text);
        if (url != null && text.trim().length() < url.length() + 40) importUrl(url);
        else importText("Texte copié", text);
    }

    private void askText() {
        final EditText field = new EditText(this);
        field.setHint("Colle ou écris ton texte ici");
        field.setMinLines(5);
        field.setGravity(Gravity.TOP);
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        LinearLayout box = new LinearLayout(this);
        int p = Ui.dp(this, 20);
        box.setPadding(p, Ui.dp(this, 8), p, 0);
        box.addView(field, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        new AlertDialog.Builder(this)
                .setTitle("Le presse-papiers est vide")
                .setView(box)
                .setPositiveButton("Lire", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface di, int w) {
                        String s = field.getText().toString();
                        if (s.trim().length() > 0) importText("Texte saisi", s);
                    }
                })
                .setNegativeButton("Annuler", null)
                .show();
    }

    private String clipboardText() {
        try {
            ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm == null || !cm.hasPrimaryClip()) return null;
            ClipData c = cm.getPrimaryClip();
            if (c == null || c.getItemCount() == 0) return null;
            CharSequence s = c.getItemAt(0).coerceToText(this);
            return s == null ? null : s.toString();
        } catch (Exception e) {
            return null;
        }
    }

    static String findUrl(String s) {
        Matcher m = Patterns.WEB_URL.matcher(s);
        while (m.find()) {
            String u = m.group();
            if (u.startsWith("http") || u.contains(".")) return u;
        }
        return null;
    }

    // ------------------------------------------------------------------ intentions reçues

    private void handleIntent(Intent i) {
        if (i == null || i.getAction() == null) return;
        String a = i.getAction();
        if (Intent.ACTION_VIEW.equals(a) && i.getData() != null) {
            Uri u = i.getData();
            if ("http".equals(u.getScheme()) || "https".equals(u.getScheme())) importUrl(u.toString());
            else importUri(u);
        } else if (Intent.ACTION_SEND.equals(a)) {
            Uri stream = i.getParcelableExtra(Intent.EXTRA_STREAM);
            String text = i.getStringExtra(Intent.EXTRA_TEXT);
            String subject = i.getStringExtra(Intent.EXTRA_SUBJECT);
            if (stream != null) importUri(stream);
            else if (text != null) {
                String url = findUrl(text);
                // Partage depuis Chrome : juste un lien (parfois précédé du titre).
                if (url != null && text.length() < url.length() + 200) importUrl(url);
                else importText(subject != null && subject.length() > 0 ? subject : "Texte partagé", text);
            }
        } else if (Intent.ACTION_PROCESS_TEXT.equals(a)) {
            CharSequence text = i.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
            if (text != null && text.toString().trim().length() > 0) importText("Texte sélectionné", text.toString());
        }
        // L'intention a été traitée : on évite de la rejouer en revenant sur l'appli.
        setIntent(new Intent(this, MainActivity.class));
    }

    // ------------------------------------------------------------------ import en arrière-plan

    private interface Job {
        Extractor.Result run(Extractor.Progress p) throws Exception;
    }

    private void importUri(final Uri uri) {
        runJob("Ouverture du document…", uri.toString(), new Job() {
            @Override public Extractor.Result run(Extractor.Progress p) throws Exception {
                return Extractor.fromUri(MainActivity.this, uri, p);
            }
        });
    }

    private void importUrl(String raw) {
        final String url = raw.trim();
        if (url.length() == 0) return;
        Prefs.setLastUrl(this, url);
        runJob("Chargement de la page…", WebExtractor.normalizeUrl(url), new Job() {
            @Override public Extractor.Result run(Extractor.Progress p) throws Exception {
                return WebExtractor.fromUrl(MainActivity.this, url, p);
            }
        });
    }

    private void importText(final String title, final String text) {
        runJob("Préparation…", "texte:" + text.hashCode(), new Job() {
            @Override public Extractor.Result run(Extractor.Progress p) {
                String t = title;
                // Titre plus parlant : le début du texte.
                String first = text.trim().split("\n")[0];
                if (first.length() > 3) t = first.length() > 60 ? first.substring(0, 57) + "…" : first;
                return Extractor.fromText(t, text);
            }
        });
    }

    private void runJob(String message, final String source, final Job job) {
        showBusy(message);
        new Thread(new Runnable() {
            @Override public void run() {
                Extractor.Result r = null;
                String error = null;
                try {
                    r = job.run(new Extractor.Progress() {
                        @Override public void onProgress(final String m) {
                            main.post(new Runnable() { @Override public void run() { if (busyText != null) busyText.setText(m); } });
                        }
                    });
                    if (r == null || r.paragraphs.isEmpty()) error = "Aucun texte lisible n'a été trouvé.";
                } catch (Extractor.UserError e) {
                    error = e.getMessage();
                } catch (OutOfMemoryError e) {
                    error = "Document trop lourd pour la mémoire du téléphone.";
                } catch (Throwable e) {
                    error = "Impossible de lire ce document (" + e.getClass().getSimpleName()
                            + (e.getMessage() != null ? " : " + e.getMessage() : "") + ").";
                }
                final Library.Entry entry = error == null ? Library.add(MainActivity.this, r, source) : null;
                final String err = error;
                main.post(new Runnable() {
                    @Override public void run() {
                        hideBusy();
                        if (isFinishing()) return;
                        if (err != null) {
                            new AlertDialog.Builder(MainActivity.this).setTitle("Oups").setMessage(err)
                                    .setPositiveButton("OK", null).show();
                        } else {
                            refresh();
                            openReader(entry.id, true);
                        }
                    }
                });
            }
        }, "import").start();
    }

    private void showBusy(String message) {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.HORIZONTAL);
        box.setGravity(Gravity.CENTER_VERTICAL);
        int p = Ui.dp(this, 24);
        box.setPadding(p, p, p, p);
        box.addView(new ProgressBar(this));
        busyText = new TextView(this);
        busyText.setText(message);
        busyText.setTextSize(TypedValue.COMPLEX_UNIT_SP, 17);
        busyText.setPadding(Ui.dp(this, 16), 0, 0, 0);
        box.addView(busyText);
        busy = new AlertDialog.Builder(this).setView(box).setCancelable(false).create();
        busy.show();
    }

    private void hideBusy() {
        if (busy != null) {
            try { busy.dismiss(); } catch (Exception ignored) {}
        }
        busy = null;
        busyText = null;
    }

    private void openReader(String id, boolean autoplay) {
        Intent i = new Intent(this, ReaderActivity.class);
        i.putExtra(ReaderActivity.EXTRA_ID, id);
        i.putExtra(ReaderActivity.EXTRA_AUTOPLAY, autoplay);
        startActivity(i);
    }

    // ------------------------------------------------------------------ réglages

    private void showSettings() {
        String[] items = {
                "Thème : " + Ui.themeName(Prefs.theme(this)),
                "Réglages de la synthèse vocale d'Android",
                "Installer d'autres voix",
                "Vider la liste des documents",
                "À propos de Lisys"};
        new AlertDialog.Builder(this)
                .setTitle("Réglages")
                .setItems(items, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int which) {
                        switch (which) {
                            case 0: chooseTheme(MainActivity.this, new Runnable() {
                                @Override public void run() { build(); refresh(); }
                            }); break;
                            case 1: openTtsSettings(MainActivity.this); break;
                            case 2: installVoices(MainActivity.this); break;
                            case 3: confirmClear(); break;
                            default: about();
                        }
                    }
                })
                .show();
    }

    static void chooseTheme(final Activity a, final Runnable done) {
        String[] names = new String[4];
        for (int i = 0; i < 4; i++) names[i] = Ui.themeName(i);
        new AlertDialog.Builder(a)
                .setTitle("Thème d'affichage")
                .setSingleChoiceItems(names, Prefs.theme(a), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int which) {
                        Prefs.setTheme(a, which);
                        d.dismiss();
                        done.run();
                    }
                })
                .show();
    }

    static void openTtsSettings(Activity a) {
        try {
            a.startActivity(new Intent("com.android.settings.TTS_SETTINGS"));
        } catch (Exception e) {
            Toast.makeText(a, "Ouvre Paramètres > Accessibilité > Synthèse vocale.", Toast.LENGTH_LONG).show();
        }
    }

    static void installVoices(Activity a) {
        try {
            a.startActivity(new Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA));
        } catch (Exception e) {
            openTtsSettings(a);
        }
    }

    private void confirmClear() {
        new AlertDialog.Builder(this)
                .setMessage("Retirer tous les documents de la liste ? (Tes fichiers d'origine ne sont pas supprimés.)")
                .setPositiveButton("Vider", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { Library.clear(MainActivity.this); refresh(); }
                })
                .setNegativeButton("Annuler", null)
                .show();
    }

    private void about() {
        String v = "";
        try { v = getPackageManager().getPackageInfo(getPackageName(), 0).versionName; } catch (Exception ignored) {}
        TextView t = new TextView(this);
        int p = Ui.dp(this, 22);
        t.setPadding(p, p, p, 0);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        t.setText("Lisys " + v + " · Echo Matras\n\n"
                + "Lecture à voix haute de PDF, Word (.docx), OpenOffice (.odt), livres EPUB, RTF, HTML, "
                + "fichiers texte et pages web.\n\n"
                + "Tout est traité sur le téléphone, avec la synthèse vocale d'Android. Aucune donnée n'est envoyée "
                + "ailleurs (sauf le téléchargement des pages web que tu demandes).\n\n"
                + "Bibliothèques : PdfBox-Android (Apache 2.0), jsoup (MIT).");
        t.setTypeface(Typeface.DEFAULT);
        new AlertDialog.Builder(this).setTitle("À propos").setView(t).setPositiveButton("OK", null).show();
    }

    private void askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission("android.permission.POST_NOTIFICATIONS") != PackageManager.PERMISSION_GRANTED
                && !getSharedPreferences("reglages", MODE_PRIVATE).getBoolean("notifAsked", false)) {
            getSharedPreferences("reglages", MODE_PRIVATE).edit().putBoolean("notifAsked", true).apply();
            requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, REQ_NOTIF);
        }
    }
}
