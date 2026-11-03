package com.qmtech.lisys;

import android.content.Context;
import android.speech.tts.TextToSpeech;

/** Petites annonces vocales de l'interface (assistant, réglages, confirmations), séparées de la lecture. */
final class Speaker {
    private Speaker() {}

    private static TextToSpeech tts;
    private static boolean ready;
    private static String pending;

    private static Runnable onDone;
    private static int counter;

    /** Parle, puis lance {@code done} à la fin de la phrase (sur le fil principal). */
    static void say(Context c, String text, Runnable done) {
        onDone = done;
        sayInternal(c, text, true);
    }

    static void say(Context c, String text) {
        onDone = null;
        sayInternal(c, text, false);
    }

    private static final android.os.Handler MAIN = new android.os.Handler(android.os.Looper.getMainLooper());

    private static void finished(String id) {
        final Runnable r = onDone;
        if (r == null || !("ui" + counter).equals(id)) return;
        onDone = null;
        MAIN.post(r);
    }

    private static void sayInternal(Context c, String text, boolean force) {
        if ((!force && !Prefs.voiceFeedback(c)) || ReaderService.playingNow) {
            if (onDone != null) { Runnable r = onDone; onDone = null; MAIN.post(r); }
            return;
        }
        counter++;
        final Context app = c.getApplicationContext();
        if (tts == null) {
            pending = text;
            tts = new TextToSpeech(app, new TextToSpeech.OnInitListener() {
                @Override public void onInit(int status) {
                    if (status != TextToSpeech.SUCCESS) return;
                    ready = true;
                    ReaderService.applyVoice(app, tts);
                    tts.setOnUtteranceProgressListener(new android.speech.tts.UtteranceProgressListener() {
                        @Override public void onStart(String id) {}
                        @Override public void onDone(String id) { finished(id); }
                        @Override public void onError(String id) { finished(id); }
                    });
                    tts.setSpeechRate(Prefs.rate(app));
                    if (pending != null) tts.speak(pending, TextToSpeech.QUEUE_FLUSH, null, "ui" + counter);
                    pending = null;
                }
            });
            return;
        }
        if (!ready) { pending = text; return; }
        tts.setSpeechRate(Prefs.rate(app));
        tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "ui" + counter);
    }

    static void stop() {
        if (tts != null && ready) tts.stop();
    }
}
