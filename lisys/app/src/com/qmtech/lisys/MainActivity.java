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

        Button photo = Ui.bigButton(this, "📷   Lire une photo (courrier, notice…)", pal.button, pal.buttonText);
        photo.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { openOcr(OcrActivity.MODE_CAMERA, null); }
        });
        photo.setOnLongClickListener(new View.OnLongClickListener() {
            @Override public boolean onLongClick(View v) { openOcr(OcrActivity.MODE_GALLERY, null); return true; }
        });
        root.addView(photo, fullWidth());
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
        root.addView(space(10));

        bubbleBtn = Ui.bigButton(this, "", pal.surface, pal.text);
        bubbleBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { showBubbleHelp(); }
        });
        root.addView(bubbleBtn, fullWidth());

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
                ? "✅   Bouton flottant activé" : "🔊   Lire les autres applis et sites");
    }

    // ------------------------------------------------------------------ bouton flottant

    private void showBubbleHelp() {
        if (ScreenReaderService.isEnabled(this)) {
            bubbleSettings();
            return;
        }
        if (!Prefs.a11yConsent(this)) {
            showAccessibilityDisclosure();
            return;
        }
        String restricted = Build.VERSION.SDK_INT >= 33
                ? "\n\nSi Android affiche « Paramètre restreint » (appli installée depuis un fichier APK) : "
                + "appuie sur « Infos appli », puis sur ⋮ en haut à droite, puis « Autoriser les paramètres restreints », "
                + "et recommence." : "";
        new AlertDialog.Builder(this)
                .setTitle("Lire les autres applis et les sites")
                .setMessage("Lisys peut afficher un bouton flottant 🔊 par-dessus toutes les applis : "
                        + "un appui, et Lisys lit à voix haute ce qui est à l'écran.\n\n"
                        + "Pour l'activer :\n1. Appuie sur « Activer »\n2. Choisis « Lisys : bouton de lecture » "
                        + "(parfois dans « Applis installées » ou « Services téléchargés »)\n3. Active-le et accepte.\n\n"
                        + "Lisys ne lit l'écran que quand tu appuies sur le bouton, et rien n'est envoyé sur internet."
                        + restricted)
                .setPositiveButton("Activer", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { openAccessibilitySettings(); }
                })
                .setNeutralButton(Build.VERSION.SDK_INT >= 33 ? "Infos appli" : null, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        try {
                            startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                    Uri.parse("package:" + getPackageName())));
                        } catch (Exception ignored) {}
                    }
                })
                .setNegativeButton("Plus tard", null)
                .show();
    }

    /**
     * Information obligatoire (règles Google Play) avant d'activer le service d'accessibilité :
     * ce que Lisys lit, pourquoi, et ce qu'il en fait. L'utilisateur doit accepter.
     */
    private void showAccessibilityDisclosure() {
        TextView t = new TextView(this);
        int p = Ui.dp(this, 22);
        t.setPadding(p, Ui.dp(this, 12), p, 0);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        t.setText("Lisys utilise le service d'accessibilité d'Android (AccessibilityService). Il est conçu pour aider "
                + "les personnes malvoyantes ou ayant des difficultés de lecture.\n\n"
                + "Ce que Lisys fait avec ce service :\n"
                + "• lire à voix haute le texte affiché à l'écran, seulement quand tu appuies sur le bouton flottant, "
                + "le bouton d'accessibilité ou les boutons de volume (si tu actives cette option) ;\n"
                + "• lire le texte sur lequel tu passes le doigt (lecture au doigt) et l'entourer en jaune ;\n"
                + "• faire défiler la page quand tu le demandes avec deux doigts ;\n"
                + "• si tu actives l'option, annoncer à voix haute les messages reçus (expéditeur et texte).\n\n"
                + "Données consultées : le texte et la position des éléments affichés à l'écran et, avec l'option "
                + "d'annonce, le contenu des notifications de messages.\n\n"
                + "Ces données sont traitées uniquement sur ton téléphone, au moment où tu le demandes. Elles ne sont "
                + "ni envoyées sur internet, ni partagées, ni vendues. Seul le dernier texte lu est gardé sur le "
                + "téléphone pour pouvoir le relire dans Lisys.\n\n"
                + "Tu peux désactiver ce service à tout moment dans Paramètres > Accessibilité.");
        ScrollView sv = new ScrollView(this);
        sv.addView(t);
        new AlertDialog.Builder(this)
                .setTitle("Autorisation d'accessibilité")
                .setView(sv)
                .setCancelable(false)
                .setPositiveButton("J'accepte", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        Prefs.setA11yConsent(MainActivity.this, true);
                        showBubbleHelp();
                    }
                })
                .setNegativeButton("Refuser", null)
                .setNeutralButton("Confidentialité", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        try {
                            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Ui.PRIVACY_URL)));
                        } catch (Exception ignored) {
                        }
                    }
                })
                .show();
    }

    /** Réglages de la bulle : taille, couleur, annonces vocales, affichage. */
    private void bubbleSettings() {
        final boolean shown = Prefs.bubble(this);
        int size = Prefs.bubbleSize(this);
        String sizeName = Ui.BUBBLE_SIZE_NAMES[1];
        for (int i = 0; i < Ui.BUBBLE_SIZES.length; i++) if (Ui.BUBBLE_SIZES[i] == size) sizeName = Ui.BUBBLE_SIZE_NAMES[i];
        int color = Math.max(0, Math.min(Prefs.bubbleColor(this), Ui.BUBBLE_COLOR_NAMES.length - 1));
        String yes = "✅ activé", no = "désactivé";
        String[] items = {
                "Taille de la bulle : " + sizeName,
                "Couleur de la bulle : " + Ui.BUBBLE_COLOR_NAMES[color],
                "Annonces vocales de la bulle : " + (Prefs.bubbleVoice(this) ? "oui" : "non"),
                shown ? "Masquer la bulle" : "Afficher la bulle",
                "Bandeau en très gros texte : " + (Prefs.caption(this) ? yes : no),
                "Boutons de volume : " + (Prefs.volumeKeys(this) ? yes : no),
                "Annoncer les messages reçus : " + (Prefs.announce(this) ? yes : no),
                "Comment ça marche ?",
                "Rapport de la dernière lecture (dépannage)",
                "Désactiver le bouton (réglages Android)"};
        new AlertDialog.Builder(this)
                .setTitle("Bouton flottant Lisys")
                .setItems(items, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        switch (w) {
                            case 0: chooseBubbleSize(); break;
                            case 1: chooseBubbleColor(); break;
                            case 2:
                                Prefs.setBubbleVoice(MainActivity.this, !Prefs.bubbleVoice(MainActivity.this));
                                bubbleSettings();
                                break;
                            case 3:
                                Prefs.setBubble(MainActivity.this, !shown);
                                bubbleSettings();
                                break;
                            case 4: captionSettings(); break;
                            case 5: volumeSettings(); break;
                            case 6: announceSettings(); break;
                            case 7: bubbleHowTo(); break;
                            case 8: showReport(); break;
                            default: openAccessibilitySettings();
                        }
                    }
                })
                .setNegativeButton("Fermer", null)
                .show();
    }

    /** Bandeau : la phrase lue s'affiche en très gros par-dessus les autres applis. */
    private void captionSettings() {
        final boolean on = Prefs.caption(this);
        int size = Prefs.captionSize(this);
        String sizeName = Ui.BUBBLE_SIZE_NAMES[1];
        for (int i = 0; i < Ui.CAPTION_SIZES.length; i++) if (Ui.CAPTION_SIZES[i] == size) sizeName = Ui.BUBBLE_SIZE_NAMES[i];
        int col = Math.max(0, Math.min(Prefs.captionColors(this), Ui.CAPTION_COLOR_NAMES.length - 1));
        String[] items = {
                on ? "Désactiver le bandeau" : "Activer le bandeau",
                "Taille du texte : " + sizeName,
                "Couleurs : " + Ui.CAPTION_COLOR_NAMES[col],
                "Position : " + (Prefs.captionTop(this) ? "en haut de l'écran" : "en bas de l'écran")};
        new AlertDialog.Builder(this)
                .setTitle("Bandeau en très gros texte")
                .setMessage(null)
                .setItems(items, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        final MainActivity a = MainActivity.this;
                        if (w == 0) { Prefs.setCaption(a, !on); captionSettings(); }
                        else if (w == 1) {
                            int cur = 1;
                            for (int i = 0; i < Ui.CAPTION_SIZES.length; i++) if (Ui.CAPTION_SIZES[i] == Prefs.captionSize(a)) cur = i;
                            new AlertDialog.Builder(a).setTitle("Taille du texte du bandeau")
                                    .setSingleChoiceItems(Ui.BUBBLE_SIZE_NAMES, cur, new DialogInterface.OnClickListener() {
                                        @Override public void onClick(DialogInterface d2, int k) {
                                            Prefs.setCaptionSize(a, Ui.CAPTION_SIZES[k]);
                                            d2.dismiss();
                                            captionSettings();
                                        }
                                    }).show();
                        } else if (w == 2) {
                            new AlertDialog.Builder(a).setTitle("Couleurs du bandeau")
                                    .setSingleChoiceItems(Ui.CAPTION_COLOR_NAMES, Prefs.captionColors(a), new DialogInterface.OnClickListener() {
                                        @Override public void onClick(DialogInterface d2, int k) {
                                            Prefs.setCaptionColors(a, k);
                                            d2.dismiss();
                                            captionSettings();
                                        }
                                    }).show();
                        } else {
                            Prefs.setCaptionTop(a, !Prefs.captionTop(a));
                            captionSettings();
                        }
                    }
                })
                .setNegativeButton("Retour", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { bubbleSettings(); }
                })
                .show();
        if (!on) {
            Toast.makeText(this, "Quand la bulle lit un mail ou un site, la phrase lue s'affiche en très gros.",
                    Toast.LENGTH_LONG).show();
        }
    }

    private void volumeSettings() {
        final boolean on = Prefs.volumeKeys(this);
        new AlertDialog.Builder(this)
                .setTitle("Boutons de volume")
                .setMessage("Avec cette option, dans n'importe quelle appli :\n\n"
                        + "• Deux appuis rapides sur VOLUME BAS : Lisys lit l'écran (ou arrête la lecture).\n"
                        + "• Rester appuyé sur VOLUME BAS (1 seconde) : lecture au doigt (ou la quitter).\n"
                        + "• Un seul appui baisse le son, comme d'habitude.\n\n"
                        + "Pendant un appel, les boutons fonctionnent normalement.")
                .setPositiveButton(on ? "Désactiver" : "Activer", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        Prefs.setVolumeKeys(MainActivity.this, !on);
                        Toast.makeText(MainActivity.this, on ? "Boutons de volume : désactivé" : "Boutons de volume : activé",
                                Toast.LENGTH_SHORT).show();
                        bubbleSettings();
                    }
                })
                .setNegativeButton("Retour", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { bubbleSettings(); }
                })
                .show();
    }

    private void announceSettings() {
        final boolean on = Prefs.announce(this);
        final boolean content = Prefs.announceContent(this);
        new AlertDialog.Builder(this)
                .setTitle("Annoncer les messages reçus")
                .setMessage("Lisys dit à voix haute qui t'écrit (SMS, WhatsApp, Messenger, Telegram, Signal, mails…)"
                        + (content ? ", puis lit le message." : ".")
                        + "\n\nRien n'est annoncé pendant un appel, en mode Ne pas déranger, ou pendant une lecture.")
                .setPositiveButton(on ? "Désactiver" : "Activer", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        Prefs.setAnnounce(MainActivity.this, !on);
                        bubbleSettings();
                    }
                })
                .setNeutralButton(content ? "Dire seulement qui écrit" : "Lire aussi le message", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        Prefs.setAnnounceContent(MainActivity.this, !content);
                        announceSettings();
                    }
                })
                .setNegativeButton("Retour", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { bubbleSettings(); }
                })
                .show();
    }

    private void chooseBubbleSize() {
        int cur = 1;
        for (int i = 0; i < Ui.BUBBLE_SIZES.length; i++) if (Ui.BUBBLE_SIZES[i] == Prefs.bubbleSize(this)) cur = i;
        new AlertDialog.Builder(this)
                .setTitle("Taille de la bulle")
                .setSingleChoiceItems(Ui.BUBBLE_SIZE_NAMES, cur, new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        // La bulle change tout de suite : on voit le résultat derrière la fenêtre.
                        Prefs.setBubbleSize(MainActivity.this, Ui.BUBBLE_SIZES[w]);
                    }
                })
                .setPositiveButton("OK", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { bubbleSettings(); }
                })
                .show();
    }

    private void chooseBubbleColor() {
        new AlertDialog.Builder(this)
                .setTitle("Couleur de la bulle")
                .setSingleChoiceItems(Ui.BUBBLE_COLOR_NAMES, Prefs.bubbleColor(this), new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { Prefs.setBubbleColor(MainActivity.this, w); }
                })
                .setPositiveButton("OK", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) { bubbleSettings(); }
                })
                .show();
    }

    private void showReport() {
        final String r = getSharedPreferences("reglages", MODE_PRIVATE).getString("rapport",
                "Pas encore de lecture avec la bulle. Ouvre l'appli ou le mail à lire, appuie sur la bulle, puis reviens ici.");
        new AlertDialog.Builder(this)
                .setTitle("Dernière lecture de l'écran")
                .setMessage(r)
                .setPositiveButton("Copier", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        ClipboardManager cm = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                        cm.setPrimaryClip(ClipData.newPlainText("Rapport Lisys", r));
                        Toast.makeText(MainActivity.this, "Rapport copié", Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton("Fermer", null)
                .show();
    }

    private void bubbleHowTo() {
        new AlertDialog.Builder(this)
                .setTitle("Comment ça marche ?")
                .setMessage("La bulle 🔊 reste par-dessus toutes les applis.\n\n"
                        + "• Un appui : Lisys lit tout le texte affiché (page web, appli, message…). "
                        + "Un deuxième appui arrête.\n\n"
                        + "• Appui long (la bulle devient ✋) : lecture au doigt. Glisse le doigt sur le texte : "
                        + "Lisys lit la phrase qui est sous le doigt et l'entoure en jaune. Quand tu lèves le doigt, "
                        + "la lecture continue. Deux doigts vers le haut ou le bas : faire défiler la page. "
                        + "Touche la bulle pour quitter ce mode.\n\n"
                        + "• Glisse la bulle pour la déplacer : elle se range contre le bord.\n\n"
                        + "Avec TalkBack, les deux actions sont dans le menu des actions de la bulle.")
                .setPositiveButton("OK", null)
                .show();
    }

    private void openAccessibilitySettings() {
        try {
            startActivity(new Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS));
        } catch (Exception e) {
            Toast.makeText(this, "Ouvre Paramètres > Accessibilité.", Toast.LENGTH_LONG).show();
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
                "text/*", "image/*", "application/xhtml+xml", "application/octet-stream"});
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
        String mime = null;
        try { mime = getContentResolver().getType(uri); } catch (Exception ignored) {}
        String ext = Extractor.extension(Extractor.displayName(this, uri));
        if ((mime != null && mime.startsWith("image/")) || ext.matches("jpe?g|png|webp|heic|heif|bmp|gif")) {
            openOcr(OcrActivity.MODE_IMAGE, uri);
            return;
        }
        runJob("Ouverture du document…", uri.toString(), new Job() {
            @Override public Extractor.Result run(Extractor.Progress p) throws Exception {
                return Extractor.fromUri(MainActivity.this, uri, p);
            }
        }, uri);
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
                    if (r == null || r.paragraphs.isEmpty()) error = "Aucun texte lisible n'a été trouvé.";
                } catch (Extractor.NeedsOcr e) {
                    error = e.getMessage();
                    scanned = true;
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
                final boolean ocr = scanned && ocrUri != null;
                main.post(new Runnable() {
                    @Override public void run() {
                        hideBusy();
                        if (isFinishing()) return;
                        if (ocr) {
                            new AlertDialog.Builder(MainActivity.this).setTitle("Document scanné")
                                    .setMessage(err + "\n\nLisys peut reconnaître le texte des pages, comme pour une photo. "
                                            + "Compte quelques secondes par page.")
                                    .setPositiveButton("Reconnaître le texte", new DialogInterface.OnClickListener() {
                                        @Override public void onClick(DialogInterface d, int w) { openOcr(OcrActivity.MODE_PDF, ocrUri); }
                                    })
                                    .setNegativeButton("Annuler", null).show();
                        } else if (err != null) {
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
                "Bouton flottant (lire les autres applis)",
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
                            case 1: showBubbleHelp(); break;
                            case 2: openTtsSettings(MainActivity.this); break;
                            case 3: installVoices(MainActivity.this); break;
                            case 4: confirmClear(); break;
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
        t.setText("Lisys " + v + " · QMTech\n\n"
                + "Lecture à voix haute de l'écran des autres applis (bouton flottant), de photos, de PDF, Word (.docx), "
                + "OpenOffice (.odt), livres EPUB, RTF, HTML, fichiers texte et pages web.\n\n"
                + "Tout est traité sur le téléphone, avec la synthèse vocale d'Android. Aucune donnée n'est envoyée "
                + "ailleurs (sauf le téléchargement des pages web que tu demandes).\n\n"
                + "Bibliothèques : PdfBox-Android (Apache 2.0), jsoup (MIT), Tesseract OCR et son modèle français "
                + "(Apache 2.0), tesseract-wasm (Apache 2.0).");
        t.setTypeface(Typeface.DEFAULT);
        new AlertDialog.Builder(this).setTitle("À propos").setView(t).setPositiveButton("OK", null)
                .setNeutralButton("Confidentialité", new DialogInterface.OnClickListener() {
                    @Override public void onClick(DialogInterface d, int w) {
                        try {
                            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(Ui.PRIVACY_URL)));
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
