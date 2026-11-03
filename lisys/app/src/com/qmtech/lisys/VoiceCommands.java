package com.qmtech.lisys;

import android.app.Activity;
import android.content.Intent;
import android.speech.RecognizerIntent;
import android.widget.Toast;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Locale;

/** Commandes vocales (reconnaissance vocale d'Android, hors ligne si la langue française est téléchargée). */
final class VoiceCommands {
    private VoiceCommands() {}

    static void listen(Activity a, int requestCode, String prompt) {
        Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, Tr.locale().toLanguageTag())
                .putExtra(RecognizerIntent.EXTRA_PROMPT, prompt)
                .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3);
        try {
            a.startActivityForResult(i, requestCode);
        } catch (Exception e) {
            Toast.makeText(a, "La reconnaissance vocale n'est pas disponible sur ce téléphone.", Toast.LENGTH_LONG).show();
            Speaker.say(a, "La reconnaissance vocale n'est pas disponible sur ce téléphone.");
        }
    }

    /** Ce qui a été dit, en minuscules et sans accents (plus simple à comparer). */
    static String heard(Intent data) {
        if (data == null) return null;
        ArrayList<String> r = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
        if (r == null || r.isEmpty()) return null;
        return r.get(0);
    }

    static String norm(String s) {
        String n = Normalizer.normalize(s.toLowerCase(Locale.FRENCH), Normalizer.Form.NFD);
        n = n.replaceAll("\\p{M}", "").replaceAll("[^a-z0-9 ]", " ").replaceAll("\\s+", " ").trim();
        if ("fr".equals(Tr.lang())) return n;
        // Anglais et espagnol : on ramène les mots aux mots-clés français reconnus par l'appli.
        StringBuilder sb = new StringBuilder();
        for (String w : n.split(" ")) {
            String fr = SYNONYMS.get(w);
            sb.append(fr != null ? fr : w).append(' ');
        }
        return sb.toString().trim();
    }

    private static final java.util.Map<String, String> SYNONYMS = new java.util.HashMap<String, String>();
    static {
        String[] p = {
                // anglais
                "read", "lis", "play", "lis", "resume", "reprendre", "pause", "pause", "stop", "stop", "next", "suivant",
                "previous", "precedent", "back", "retour", "repeat", "repete", "again", "encore", "faster", "vite",
                "slower", "lent", "slowly", "lentement", "bigger", "gros", "larger", "gros", "smaller", "petit",
                "beginning", "debut", "start", "commencer", "bookmark", "signet", "bookmarks", "signets", "search", "cherche",
                "find", "cherche", "magnifier", "loupe", "home", "accueil", "yes", "oui", "no", "non", "continue", "continuer",
                "skip", "passer", "later", "tard", "photo", "photo", "picture", "photo", "letter", "courrier", "document", "document",
                "file", "fichier", "website", "site", "page", "page", "copied", "copie", "clipboard", "presse", "contrast", "contraste",
                "buttons", "boutons", "big", "gros", "allow", "autoriser", "enable", "activer", "settings", "reglages", "paragraph", "paragraphe",
                // espagnol
                "lee", "lis", "leer", "lis", "reanudar", "reprendre", "sigue", "continue", "pausa", "pause", "para", "stop", "detente", "stop",
                "siguiente", "suivant", "anterior", "precedent", "repite", "repete", "otra", "encore", "rapido", "vite", "lento", "lent",
                "despacio", "lentement", "grande", "gros", "grandes", "gros", "pequeno", "petit", "inicio", "debut", "empezar", "commencer",
                "marcador", "signet", "marcadores", "signets", "busca", "cherche", "buscar", "cherche", "lupa", "loupe", "volver", "retour",
                "si", "oui", "vale", "oui", "continuar", "continuer", "saltar", "passer", "luego", "tard", "foto", "photo", "carta", "courrier",
                "documento", "document", "archivo", "fichier", "web", "site", "pagina", "page", "copiado", "copie", "portapapeles", "presse",
                "botones", "boutons", "permitir", "autoriser", "activar", "activer", "ajustes", "reglages", "parrafo", "paragraphe"};
        for (int i = 0; i + 1 < p.length; i += 2) SYNONYMS.put(p[i], p[i + 1]);
    }

    /** Vrai si la phrase contient l'un des mots-clés (sans accents). */
    static boolean has(String said, String... words) {
        String s = " " + said + " ";
        for (String w : words) if (s.contains(" " + w + " ")) return true;
        return false;
    }
}
