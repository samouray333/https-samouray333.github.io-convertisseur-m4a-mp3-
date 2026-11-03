package com.qmtech.lisys;

import android.content.Context;
import android.speech.tts.TextToSpeech;

/** Petites annonces vocales de l'interface (assistant, réglages, confirmations), séparées de la lecture. */
final class Speaker {
    private Speaker() {}

    private static TextToSpeech tts;
    private static boolean ready;
    private static String pending;

    static void say(Context c, String text) {
        if (!Prefs.voiceFeedback(c) || ReaderService.playingNow) return;
        final Context app = c.getApplicationContext();
        if (tts == null) {
            pending = text;
            tts = new TextToSpeech(app, new TextToSpeech.OnInitListener() {
                @Override public void onInit(int status) {
                    if (status != TextToSpeech.SUCCESS) return;
                    ready = true;
                    ReaderService.applyVoice(app, tts);
                    tts.setSpeechRate(Prefs.rate(app));
                    if (pending != null) tts.speak(pending, TextToSpeech.QUEUE_FLUSH, null, "ui");
                    pending = null;
                }
            });
            return;
        }
        if (!ready) { pending = text; return; }
        tts.setSpeechRate(Prefs.rate(app));
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "ui");
    }

    static void stop() {
        if (tts != null && ready) tts.stop();
    }
}
