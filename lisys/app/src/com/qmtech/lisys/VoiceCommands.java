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
                .putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
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
        return n.replaceAll("\\p{M}", "").replaceAll("[^a-z0-9 ]", " ").replaceAll("\\s+", " ").trim();
    }

    /** Vrai si la phrase contient l'un des mots-clés (sans accents). */
    static boolean has(String said, String... words) {
        String s = " " + said + " ";
        for (String w : words) if (s.contains(" " + w + " ")) return true;
        return false;
    }
}
