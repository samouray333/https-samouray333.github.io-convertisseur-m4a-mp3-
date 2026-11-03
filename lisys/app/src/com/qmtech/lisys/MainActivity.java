package com.qmtech.lisys;

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
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;

/** Écran d'accueil : ouvrir un document, une page web, du texte, ou reprendre une lecture. */
public class MainActivity extends Activity {

    private static final int REQ_OPEN = 1;
    private static final int REQ_NOTIF = 2;
    private static final int REQ_VOICE = 3;
    static final String ACTION_READ_CLIPBOARD = "com.qmtech.lisys.READ_CLIPBOARD";
    private boolean clipboardPending;

    private final Handler main = new Handler(Looper.getMainLooper());
    private Ui.Palette pal;
    private ListView list;
    private TextView empty;
    private Button bubbleBtn;
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
        if (state == null && !Prefs.setupDone(this)) startActivity(new Intent(this, SetupActivity.class));
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
        titles.addView(Ui.label(this, Tr.t("Tes documents et pages web lus à voix haute"), 15, pal.muted, false));
        head.addView(titles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        TextView gear = Ui.roundButton(this, "⚙", Tr.t("Réglages"), pal.surface, pal.text, 52);
        gear.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { openSettings(); }
        });
        TextView mic = Ui.roundButton(this, "🎤", Tr.t("Commande vocale"), pal.surface, pal.text, 52);
        mic.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                VoiceCommands.listen(MainActivity.this, REQ_VOICE, Tr.t("Dis : photo, loupe, document, page web, texte copié ou reprendre"));
            }
        });
        head.addView(mic);
        head.addView(gear);
        root.addView(head);

        root.addView(space(14));
        Button open = Ui.bigButton(this, Tr.t("📄   Ouvrir un document"), pal.button, pal.buttonText);
        open.setContentDescription(Tr.t("Ouvrir un document : PDF, Word, livre EPUB, texte"));
        open.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { pickDocument(); }
        });
        root.addView(open, fullWidth());
        root.addView(space(10));

        Button photo = Ui.bigButton(this, Tr.t("📷   Lire une photo (courrier, notice…)"), pal.button, pal.buttonText);
        photo.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { openOcr(OcrActivity.MODE_CAMERA, null); }
        });
        photo.setOnLongClickListener(new View.OnLongClickListener() {
            @Override public boolean onLongClick(View v) { openOcr(OcrActivity.MODE_GALLERY, null); return true; }
        });
        root.addView(photo, fullWidth());
        root.addView(space(10));

        Button loupe = Ui.bigButton(this, Tr.t("🔍   Loupe (agrandir avec l'appareil photo)"), pal.button, pal.buttonText);
        loupe.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { startActivity(new Intent(MainActivity.this, MagnifierActivity.class)); }
        });
        root.addView(loupe, fullWidth());
        root.addView(space(10));

        Button web = Ui.bigButton(this, Tr.t("🌐   Lire une page web"), pal.button, pal.buttonText);
        web.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { askUrl(); }
        });
        root.addView(web, fullWidth());
        root.addView(space(10));

        Button clip = Ui.bigButton(this, Tr.t("📋   Lire le texte copié"), pal.surface, pal.text);
        clip.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { readClipboard(); }
        });
        root.addView(clip, fullWidth());
        root.addView(space(10));

        bubbleBtn = Ui.bigButton(this, "", pal.surface, pal.text);
        bubbleBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { showBubbleHelp(); }
        });
        root.addView(bubbleBtn, fullWidth());

        root.addView(space(20));
        root.addView(Ui.label(this, Tr.t("Reprendre la lecture"), 18, pal.text, true));
        root.addView(space(6));

        empty = Ui.label(this, Tr.t("Aucun document pour l'instant.\n\nAstuce : dans n'importe quelle appli, ")
                + Tr.t("sélectionne du texte puis choisis « Lire avec Lisys ». Tu peux aussi partager une page ")
                + Tr.t("depuis Chrome ou un fichier depuis Mes fichiers vers Lisys."), 16, pal.muted, false);
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
        Ui.setContent(this, root);
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
        bubbleBtn.setText(ScreenReaderService.isEnabled(this)
                ? Tr.t("✅   Bouton flottant activé") : Tr.t("🔊   Lire les autres applis et sites"));
    }

    // ------------------------------------------------------------------ bouton flottant

    private void showBubbleHelp() {
        if (!Features.require(this, Tr.t("Le bouton flottant"))) return;
        if (ScreenReaderService.isEnabled(this)) {
            openSettings();
            return;
        }
        if (!Prefs.a11yConsent(this)) {
            showAccessibilityDisclosure(this, new Runnable() { @Override public void run() { showBubbleHelp(); } });
            return;
        }
        String restricted = Build.VERSION.SDK_INT >= 33
                ? Tr.t("\n\nSi Android affiche « Paramètre restreint » (appli installée depuis un fichier APK) : ")
                + Tr.t("appuie sur « Infos appli », puis sur ⋮ en haut à droite, puis « Autoriser les paramètres restreints », ")
                + Tr.t("et recommence.") : "";
        Ui.dialog(this)
                .setTitle(Tr.t("Lire les autres applis et les sites"))
                .setMessage(Tr.t("Lisys peut afficher un bouton flottant 🔊 par-dessus toutes les applis : ")
                        + Tr.t("un appui, et Lisys lit à voix haute ce qui est à l'écran.\n\n")
                        + Tr.t("Pour l'activer :\n1. Appuie sur « Activer »\n2. Choisis « Lisys : bouton de lecture » ")
                        + Tr.t("(parfois dans « Applis installées » ou « Services téléchargés »)\n3. Active-le et accepte.\n\n")
                        + Tr.t("Lisys ne lit l'écran que quand tu appuies sur le bouton, et rien n'est envoyé sur internet.")
                        + restricted)
                .setPositiveButton(Tr.t("Activer"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { openAccessibilitySettings(MainActivity.this); }
                })
                .setNeutralButton(Build.VERSION.SDK_INT >= 33 ? Tr.t("Infos appli") : null, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        try {
                            startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                    Uri.parse("package:" + getPackageName())));
                        } catch (Exception ignored) {}
                    }
                })
                .setNegativeButton(Tr.t("Plus tard"), null)
                .show();
    }

    /**
     * Information obligatoire (règles Google Play) avant d'activer le service d'accessibilité :
     * ce que Lisys lit, pourquoi, et ce qu'il en fait. L'utilisateur doit accepter.
     */
    static void showAccessibilityDisclosure(final Activity a, final Runnable onAccept) {
        TextView t = new TextView(a);
        int p = Ui.dp(a, 22);
        t.setPadding(p, Ui.dp(a, 12), p, 0);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        t.setText(Tr.t("Lisys utilise le service d'accessibilité d'Android (AccessibilityService). Il est conçu pour aider ")
                + Tr.t("les personnes malvoyantes ou ayant des difficultés de lecture.\n\n")
                + Tr.t("Ce que Lisys fait avec ce service :\n")
                + Tr.t("• lire à voix haute le texte affiché à l'écran, seulement quand tu appuies sur le bouton flottant, ")
                + Tr.t("le bouton d'accessibilité ou les boutons de volume (si tu actives cette option) ;\n")
                + Tr.t("• lire le texte sur lequel tu passes le doigt (lecture au doigt) et l'entourer en jaune ;\n")
                + Tr.t("• faire défiler la page quand tu le demandes avec deux doigts ;\n")
                + Tr.t("• si tu actives l'option, annoncer à voix haute les messages reçus (expéditeur et texte).\n\n")
                + Tr.t("Données consultées : le texte et la position des éléments affichés à l'écran et, avec l'option ")
                + Tr.t("d'annonce, le contenu des notifications de messages.\n\n")
                + Tr.t("Ces données sont traitées uniquement sur ton téléphone, au moment où tu le demandes. Elles ne sont ")
                + Tr.t("ni envoyées sur internet, ni partagées, ni vendues. Seul le dernier texte lu est gardé sur le ")
                + Tr.t("téléphone pour pouvoir le relire dans Lisys.\n\n")
                + Tr.t("Tu peux désactiver ce service à tout moment dans Paramètres > Accessibilité."));
        ScrollView sv = new ScrollView(a);
        sv.addView(t);
        Ui.dialog(a)
                .setTitle(Tr.t("Autorisation d'accessibilité"))
                .setView(sv)
                .setCancelable(false)
                .setPositiveButton(Tr.t("J'accepte"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        Prefs.setA11yConsent(a, true);
                        if (onAccept != null) onAccept.run();
                    }
                })
                .setNegativeButton(Tr.t("Refuser"), null)
                .setNeutralButton(Tr.t("Confidentialité"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        try {
                            a.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Ui.PRIVACY_URL)));
                        } catch (Exception ignored) {
                        }
                    }
                })
                .show();
    }

    static void showReport(final Activity a) {
        final String r = a.getSharedPreferences("reglages", Context.MODE_PRIVATE).getString("rapport",
                Tr.t("Pas encore de lecture avec la bulle. Ouvre l'appli ou le mail à lire, appuie sur la bulle, puis reviens ici."));
        Ui.dialog(a)
                .setTitle(Tr.t("Dernière lecture de l'écran"))
                .setMessage(r)
                .setPositiveButton(Tr.t("Copier"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        ClipboardManager cm = (ClipboardManager) a.getSystemService(Context.CLIPBOARD_SERVICE);
                        cm.setPrimaryClip(ClipData.newPlainText(Tr.t("Rapport Lisys"), r));
                        Toast.makeText(a, Tr.t("Rapport copié"), Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton(Tr.t("Fermer"), null)
                .show();
    }

    static void bubbleHowTo(final Activity a) {
        Ui.dialog(a)
                .setTitle(Tr.t("Comment ça marche ?"))
                .setMessage(Tr.t("La bulle 🔊 reste par-dessus toutes les applis.\n\n")
                        + Tr.t("• Un appui : Lisys lit tout le texte affiché (page web, appli, message…). ")
                        + Tr.t("Un deuxième appui arrête.\n\n")
                        + Tr.t("• Appui long (la bulle devient ✋) : lecture au doigt. Glisse le doigt sur le texte : ")
                        + Tr.t("Lisys lit seulement la phrase qui est sous le doigt et l'entoure en jaune. Déplace le doigt pour ")
                        + Tr.t("lire une autre phrase (option dans les réglages pour continuer jusqu'en bas). Deux doigts vers le haut ou le bas : faire défiler la page. ")
                        + Tr.t("Touche la bulle pour quitter ce mode.\n\n")
                        + Tr.t("• Glisse la bulle pour la déplacer : elle se range contre le bord.\n\n")
                        + Tr.t("Avec TalkBack, les deux actions sont dans le menu des actions de la bulle."))
                .setPositiveButton("OK", null)
                .show();
    }

    static void openAccessibilitySettings(final Activity a) {
        try {
            a.startActivity(new Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS));
        } catch (Exception e) {
            Toast.makeText(a, Tr.t("Ouvre Paramètres > Accessibilité."), Toast.LENGTH_LONG).show();
        }
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
            meta.setText(e.kind + Tr.t("  ·  lu à ") + e.percent() + " %  ·  " + when);
            row.setContentDescription(e.title + ", " + e.kind + Tr.t(", lu à ") + e.percent() + Tr.t(" pour cent"));
            return row;
        }
    }

    private void confirmRemove(final Library.Entry e) {
        Ui.dialog(this)
                .setTitle(e.title)
                .setItems(new String[]{Tr.t("Lire depuis le début"), Tr.t("Retirer de la liste")}, new DialogInterface.OnClickListener() {
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
                "application/epub+zip", "application/zip",
                "application/rtf", "text/rtf",
                "text/*", "image/*", "application/xhtml+xml", "application/octet-stream"});
        try {
            startActivityForResult(i, REQ_OPEN);
        } catch (Exception e) {
            Toast.makeText(this, Tr.t("Aucun gestionnaire de fichiers disponible."), Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        super.onActivityResult(req, res, data);
        if (req == REQ_VOICE && res == RESULT_OK) { homeCommand(VoiceCommands.heard(data)); return; }
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
        help.setText(Tr.t("« Lire » récupère le texte de l'article directement. Si la page demande une connexion ")
                + Tr.t("ou ne s'affiche pas bien, choisis « Navigateur »."));
        help.setPadding(0, Ui.dp(this, 8), 0, 0);
        box.addView(help);
        final AlertDialog d = Ui.dialog(this)
                .setTitle(Tr.t("Lire une page web"))
                .setView(box)
                .setPositiveButton(Tr.t("Lire"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface di, int w) { importUrl(field.getText().toString()); }
                })
                .setNeutralButton(Tr.t("Navigateur"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface di, int w) {
                        String u = field.getText().toString().trim();
                        Intent i = new Intent(MainActivity.this, WebActivity.class);
                        if (u.length() > 0) i.putExtra(WebActivity.EXTRA_URL, u);
                        startActivity(i);
                    }
                })
                .setNegativeButton(Tr.t("Annuler"), null)
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
        else importText(Tr.t("Texte copié"), text);
    }

    private void askText() {
        final EditText field = new EditText(this);
        field.setHint(Tr.t("Colle ou écris ton texte ici"));
        field.setMinLines(5);
        field.setGravity(Gravity.TOP);
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        LinearLayout box = new LinearLayout(this);
        int p = Ui.dp(this, 20);
        box.setPadding(p, Ui.dp(this, 8), p, 0);
        box.addView(field, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        Ui.dialog(this)
                .setTitle(Tr.t("Le presse-papiers est vide"))
                .setView(box)
                .setPositiveButton(Tr.t("Lire"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface di, int w) {
                        String s = field.getText().toString();
                        if (s.trim().length() > 0) importText(Tr.t("Texte saisi"), s);
                    }
                })
                .setNegativeButton(Tr.t("Annuler"), null)
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

    /** Commandes vocales de l'accueil. */
    private void homeCommand(String raw) {
        if (raw == null) return;
        String c = VoiceCommands.norm(raw);
        if (VoiceCommands.has(c, "loupe", "agrandir", "zoom")) startActivity(new Intent(this, MagnifierActivity.class));
        else if (VoiceCommands.has(c, "photo", "courrier", "papier", "camera", "lettre")) openOcr(OcrActivity.MODE_CAMERA, null);
        else if (VoiceCommands.has(c, "document", "fichier", "pdf", "livre")) pickDocument();
        else if (VoiceCommands.has(c, "web", "site", "internet", "page")) askUrl();
        else if (VoiceCommands.has(c, "copie", "presse", "colle", "coller")) readClipboard();
        else if (VoiceCommands.has(c, "reprendre", "reprends", "continue", "dernier", "lis", "lire")) {
            List<Library.Entry> l = Library.list(this);
            if (l.isEmpty()) Speaker.say(this, Tr.t("Aucun document à reprendre."));
            else openReader(l.get(0).id, true);
        } else if (VoiceCommands.has(c, "reglage", "reglages", "parametre", "parametres")) openSettings();
        else Speaker.say(this, Tr.t("Je n'ai pas compris : ") + raw + Tr.t(". Dis par exemple : photo, loupe, document, ou reprendre."));
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        // Android 10+ : le presse-papiers ne se lit qu'une fois la fenêtre au premier plan (widget, raccourci).
        if (hasFocus && clipboardPending) { clipboardPending = false; readClipboard(); }
    }

    private void handleIntent(Intent i) {
        if (i != null && ACTION_READ_CLIPBOARD.equals(i.getAction())) {
            clipboardPending = true;
            setIntent(new Intent(this, MainActivity.class));
            return;
        }
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
                else importText(subject != null && subject.length() > 0 ? subject : Tr.t("Texte partagé"), text);
            }
        } else if (Intent.ACTION_PROCESS_TEXT.equals(a)) {
            CharSequence text = i.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT);
            if (text != null && text.toString().trim().length() > 0) importText(Tr.t("Texte sélectionné"), text.toString());
        }
        // L'intention a été traitée : on évite de la rejouer en revenant sur l'appli.
        setIntent(new Intent(this, MainActivity.class));
    }

    // ------------------------------------------------------------------ import en arrière-plan

    private interface Job {
        Extractor.Result run(Extractor.Progress p) throws Exception;
    }

    private void importUri(final Uri uri) {
        String mime = null;
        try { mime = getContentResolver().getType(uri); } catch (Exception ignored) {}
        String ext = Extractor.extension(Extractor.displayName(this, uri));
        if ((mime != null && mime.startsWith("image/")) || ext.matches("jpe?g|png|webp|heic|heif|bmp|gif")) {
            openOcr(OcrActivity.MODE_IMAGE, uri);
            return;
        }
        runJob(Tr.t("Ouverture du document…"), uri.toString(), new Job() {
            @Override public Extractor.Result run(Extractor.Progress p) throws Exception {
                return Extractor.fromUri(MainActivity.this, uri, p);
            }
        }, uri);
    }

    private void importUrl(String raw) {
        final String url = raw.trim();
        if (url.length() == 0) return;
        Prefs.setLastUrl(this, url);
        runJob(Tr.t("Chargement de la page…"), WebExtractor.normalizeUrl(url), new Job() {
            @Override public Extractor.Result run(Extractor.Progress p) throws Exception {
                return WebExtractor.fromUrl(MainActivity.this, url, p);
            }
        });
    }

    private void importText(final String title, final String text) {
        runJob(Tr.t("Préparation…"), "texte:" + text.hashCode(), new Job() {
            @Override public Extractor.Result run(Extractor.Progress p) {
                String t = title;
                // Titre plus parlant : le début du texte.
                String first = text.trim().split("\n")[0];
                if (first.length() > 3) t = first.length() > 60 ? first.substring(0, 57) + "…" : first;
                return Extractor.fromText(t, text);
            }
        });
    }

    private void openOcr(String mode, Uri data) {
        Intent i = new Intent(this, OcrActivity.class).putExtra(OcrActivity.EXTRA_MODE, mode);
        if (data != null) {
            i.setData(data);
            i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        }
        startActivity(i);
    }

    private void runJob(String message, final String source, final Job job) {
        runJob(message, source, job, null);
    }

    /** ocrUri : document à proposer à la reconnaissance de texte si c'est un PDF scanné. */
    private void runJob(String message, final String source, final Job job, final Uri ocrUri) {
        showBusy(message);
        new Thread(new Runnable() {
            @Override public void run() {
                Extractor.Result r = null;
                String error = null;
                boolean scanned = false;
                try {
                    r = job.run(new Extractor.Progress() {
                        @Override public void onProgress(final String m) {
                            main.post(new Runnable() { @Override public void run() { if (busyText != null) busyText.setText(m); } });
                        }
                    });
                    if (r == null || r.paragraphs.isEmpty()) error = Tr.t("Aucun texte lisible n'a été trouvé.");
                } catch (Extractor.NeedsOcr e) {
                    error = e.getMessage();
                    scanned = true;
                } catch (Extractor.UserError e) {
                    error = e.getMessage();
                } catch (OutOfMemoryError e) {
                    error = Tr.t("Document trop lourd pour la mémoire du téléphone.");
                } catch (Throwable e) {
                    error = Tr.t("Impossible de lire ce document (") + e.getClass().getSimpleName()
                            + (e.getMessage() != null ? " : " + e.getMessage() : "") + ").";
                }
                final Library.Entry entry = error == null ? Library.add(MainActivity.this, r, source) : null;
                final String err = error;
                final boolean ocr = scanned && ocrUri != null;
                main.post(new Runnable() {
                    @Override public void run() {
                        hideBusy();
                        if (isFinishing()) return;
                        if (ocr) {
                            Ui.dialog(MainActivity.this).setTitle(Tr.t("Document scanné"))
                                    .setMessage(err + Tr.t("\n\nLisys peut reconnaître le texte des pages, comme pour une photo. ")
                                            + Tr.t("Compte quelques secondes par page."))
                                    .setPositiveButton(Tr.t("Reconnaître le texte"), new DialogInterface.OnClickListener() {
                                        @Override public void onClick(DialogInterface d, int w) { openOcr(OcrActivity.MODE_PDF, ocrUri); }
                                    })
                                    .setNegativeButton(Tr.t("Annuler"), null).show();
                        } else if (err != null) {
                            Ui.dialog(MainActivity.this).setTitle(Tr.t("Oups")).setMessage(err)
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
        busy = Ui.dialog(this).setView(box).setCancelable(false).create();
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

    private void openSettings() {
        startActivity(new Intent(this, SettingsActivity.class));
    }

    static void chooseTheme(final Activity a, final Runnable done) {
        String[] names = new String[4];
        for (int i = 0; i < 4; i++) names[i] = Ui.themeName(i);
        Ui.dialog(a)
                .setTitle(Tr.t("Thème d'affichage"))
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
            Toast.makeText(a, Tr.t("Ouvre Paramètres > Accessibilité > Synthèse vocale."), Toast.LENGTH_LONG).show();
        }
    }

    static void installVoices(Activity a) {
        try {
            a.startActivity(new Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA));
        } catch (Exception e) {
            openTtsSettings(a);
        }
    }

    static void confirmClear(final Activity a) {
        Ui.dialog(a)
                .setMessage(Tr.t("Retirer tous les documents de la liste ? (Tes fichiers d'origine ne sont pas supprimés.)"))
                .setPositiveButton(Tr.t("Vider"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { Library.clear(a); }
                })
                .setNegativeButton(Tr.t("Annuler"), null)
                .show();
    }

    static void about(final Activity a) {
        String v = "";
        try { v = a.getPackageManager().getPackageInfo(a.getPackageName(), 0).versionName; } catch (Exception ignored) {}
        TextView t = new TextView(a);
        int p = Ui.dp(a, 22);
        t.setPadding(p, p, p, 0);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 15);
        t.setText("Lisys " + v + " · QMTech\n\n"
                + Tr.t("Lecture à voix haute de l'écran des autres applis (bouton flottant), de photos, de PDF, Word (.docx), ")
                + Tr.t("OpenOffice (.odt), livres EPUB, RTF, HTML, fichiers texte et pages web.\n\n")
                + Tr.t("Tout est traité sur le téléphone, avec la synthèse vocale d'Android. Aucune donnée n'est envoyée ")
                + Tr.t("ailleurs (sauf le téléchargement des pages web que tu demandes).\n\n")
                + Tr.t("Bibliothèques : PdfBox-Android (Apache 2.0), jsoup (MIT), Tesseract OCR et son modèle français ")
                + "(Apache 2.0), tesseract-wasm (Apache 2.0).");
        t.setTypeface(Typeface.DEFAULT);
        Ui.dialog(a).setTitle(Tr.t("À propos")).setView(t).setPositiveButton("OK", null)
                .setNeutralButton(Tr.t("Confidentialité"), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        try {
                            a.startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Ui.PRIVACY_URL)));
                        } catch (Exception ignored) {
                        }
                    }
                }).show();
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
