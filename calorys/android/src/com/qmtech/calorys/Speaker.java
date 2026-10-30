package com.qmtech.calorys;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;

import java.util.Locale;

/**
 * Lecture à voix haute des rappels (synthèse vocale du téléphone, en français).
 * Muette en mode silencieux ou vibreur et pendant un appel ; le volume est celui des notifications.
 */
final class Speaker {
    private Speaker() {}

    static boolean canSpeak(Context ctx) {
        AudioManager am = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
        if (am == null) return false;
        int mode = am.getMode();
        return am.getRingerMode() == AudioManager.RINGER_MODE_NORMAL
                && mode != AudioManager.MODE_IN_CALL && mode != AudioManager.MODE_IN_COMMUNICATION;
    }

    /** Lit le texte puis appelle done (au plus tard après maxMs). */
    static void say(Context ctx, final String text, long maxMs, final Runnable done) {
        final Handler h = new Handler(Looper.getMainLooper());
        final TextToSpeech[] t = new TextToSpeech[1];
        final boolean[] finished = {false};
        final Runnable end = new Runnable() {
            @Override
            public void run() {
                if (finished[0]) return;
                finished[0] = true;
                try { if (t[0] != null) t[0].shutdown(); } catch (Exception e) { /* ignore */ }
                if (done != null) done.run();
            }
        };
        h.postDelayed(end, maxMs);
        t[0] = new TextToSpeech(ctx.getApplicationContext(), new TextToSpeech.OnInitListener() {
            @Override
            public void onInit(int status) {
                TextToSpeech tts = t[0];
                if (status != TextToSpeech.SUCCESS || tts == null || finished[0]) { h.post(end); return; }
                if (tts.setLanguage(Locale.FRANCE) < 0) tts.setLanguage(Locale.FRENCH);
                tts.setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_NOTIFICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
                tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                    @Override public void onStart(String id) { }
                    @Override public void onDone(String id) { h.post(end); }
                    @Override public void onError(String id) { h.post(end); }
                });
                if (tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "calorys") != TextToSpeech.SUCCESS) h.post(end);
            }
        });
    }
}
