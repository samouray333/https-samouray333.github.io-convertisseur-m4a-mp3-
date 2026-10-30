package com.qmtech.lisys;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Binder;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.speech.tts.Voice;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Service de lecture à voix haute. Il continue de lire écran éteint ou appli en arrière-plan,
 * avec les commandes dans la notification, sur l'écran de verrouillage et les boutons du casque.
 */
public class ReaderService extends Service implements TextToSpeech.OnInitListener {

    public static final String ACTION_TOGGLE = "com.qmtech.lisys.TOGGLE";
    public static final String ACTION_NEXT = "com.qmtech.lisys.NEXT";
    public static final String ACTION_PREV = "com.qmtech.lisys.PREV";
    public static final String ACTION_STOP = "com.qmtech.lisys.STOP";

    private static final String CHANNEL = "lecture";
    private static final int NOTIF_ID = 1;
    /** Nombre de phrases envoyées d'avance au moteur vocal, pour éviter les blancs. */
    private static final int LOOKAHEAD = 3;

    public interface Listener {
        void onPosition(int para, int sentence);
        void onWord(int para, int start, int end);
        void onState(boolean playing);
        void onTtsReady(boolean ok, String error);
        void onFinished();
        void onDocumentChanged();
    }

    public final class LocalBinder extends Binder {
        public ReaderService service() { return ReaderService.this; }
    }

    private final IBinder binder = new LocalBinder();
    private final Handler main = new Handler(Looper.getMainLooper());
    private final List<Listener> listeners = new ArrayList<Listener>();

    private TextToSpeech tts;
    private boolean ttsReady;
    private String ttsError;
    private boolean pendingPlay;

    private String docId;
    private String title = "";
    private List<String> paras = new ArrayList<String>();
    private final List<List<int[]>> sentCache = new ArrayList<List<int[]>>();

    private int para, sent;          // phrase en cours de lecture
    private int qPara, qSent;        // prochaine phrase à envoyer au moteur
    private int queued;              // phrases en attente dans le moteur
    private int generation;          // change à chaque arrêt / saut, pour ignorer les anciens rappels
    private boolean playing;
    private boolean pausedByFocus;
    private long lastSave;
    private long sleepAt;            // minuterie de sommeil (0 = aucune)

    private MediaSession session;
    private AudioManager audio;
    private AudioFocusRequest focusRequest;
    private boolean noisyRegistered;

    private final BroadcastReceiver noisy = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) {
            if (AudioManager.ACTION_AUDIO_BECOMING_NOISY.equals(i.getAction())) pause();
        }
    };

    private final Runnable sleepTask = new Runnable() {
        @Override public void run() {
            sleepAt = 0;
            pause();
        }
    };

    // ------------------------------------------------------------------ cycle de vie

    @Override
    public void onCreate() {
        super.onCreate();
        audio = (AudioManager) getSystemService(AUDIO_SERVICE);
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        NotificationChannel ch = new NotificationChannel(CHANNEL, "Lecture à voix haute", NotificationManager.IMPORTANCE_LOW);
        ch.setShowBadge(false);
        nm.createNotificationChannel(ch);

        session = new MediaSession(this, "Lisys");
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() { play(); }
            @Override public void onPause() { pause(); }
            @Override public void onSkipToNext() { next(); }
            @Override public void onSkipToPrevious() { previous(); }
            @Override public void onStop() { pause(); }
            @Override public void onFastForward() { nextParagraph(); }
            @Override public void onRewind() { previousParagraph(); }
        });
        session.setActive(true);
        startTts();
    }

    private void startTts() {
        ttsReady = false;
        ttsError = null;
        tts = new TextToSpeech(this, this);
    }

    @Override
    public void onInit(int status) {
        if (status != TextToSpeech.SUCCESS) {
            ttsError = "Aucun moteur de synthèse vocale n'est disponible. Installe « Services de reconnaissance "
                    + "et de synthèse vocale de Google » depuis le Play Store, puis relance Lisys.";
            for (Listener l : copyListeners()) l.onTtsReady(false, ttsError);
            return;
        }
        tts.setAudioAttributes(new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build());
        applyVoice(this, tts);
        tts.setSpeechRate(Prefs.rate(this));
        tts.setPitch(Prefs.pitch(this));
        tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(final String id) {
                main.post(new Runnable() { @Override public void run() { onUtteranceStart(id); } });
            }
            @Override public void onDone(final String id) {
                main.post(new Runnable() { @Override public void run() { onUtteranceDone(id); } });
            }
            @Override public void onError(final String id) {
                main.post(new Runnable() { @Override public void run() { onUtteranceDone(id); } });
            }
            @Override public void onError(final String id, int code) {
                main.post(new Runnable() { @Override public void run() { onUtteranceDone(id); } });
            }
            @Override public void onRangeStart(final String id, final int start, final int end, int frame) {
                main.post(new Runnable() { @Override public void run() { onRange(id, start, end); } });
            }
        });
        ttsReady = true;
        for (Listener l : copyListeners()) l.onTtsReady(true, null);
        if (pendingPlay) {
            pendingPlay = false;
            play();
        }
    }

    /** Applique la voix choisie dans les réglages, sinon une voix française si possible. */
    static void applyVoice(Context c, TextToSpeech tts) {
        String wanted = Prefs.voice(c);
        if (wanted.length() > 0) {
            try {
                Set<Voice> voices = tts.getVoices();
                if (voices != null) {
                    for (Voice v : voices) {
                        if (v.getName().equals(wanted)) {
                            tts.setVoice(v);
                            return;
                        }
                    }
                }
            } catch (Exception ignored) {
            }
        }
        Locale fr = Locale.FRANCE;
        if (tts.isLanguageAvailable(fr) >= TextToSpeech.LANG_AVAILABLE) tts.setLanguage(fr);
        else tts.setLanguage(Locale.getDefault());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && intent.getAction() != null) {
            String a = intent.getAction();
            if (ACTION_TOGGLE.equals(a)) toggle();
            else if (ACTION_NEXT.equals(a)) next();
            else if (ACTION_PREV.equals(a)) previous();
            else if (ACTION_STOP.equals(a)) {
                pause();
                stopForegroundCompat(true);
                stopSelf();
            }
        }
        return START_NOT_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) { return binder; }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // L'appli est balayée des applis récentes : si on ne lit pas, on s'arrête.
        if (!playing) stopSelf();
    }

    @Override
    public void onDestroy() {
        savePosition(true);
        playing = false;
        main.removeCallbacks(sleepTask);
        abandonFocus();
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        session.release();
        super.onDestroy();
    }

    // ------------------------------------------------------------------ écouteurs

    public void addListener(Listener l) {
        if (!listeners.contains(l)) listeners.add(l);
        if (ttsReady) l.onTtsReady(true, null);
        else if (ttsError != null) l.onTtsReady(false, ttsError);
    }

    public void removeListener(Listener l) { listeners.remove(l); }

    private List<Listener> copyListeners() { return new ArrayList<Listener>(listeners); }

    // ------------------------------------------------------------------ document

    /** Charge un document de la bibliothèque (ne fait rien si c'est déjà celui en cours). */
    public void load(String id) { load(id, false); }

    /** force = recharger même si c'est le document en cours (texte de l'écran qui a changé). */
    public void load(String id, boolean force) {
        if (id.equals(docId) && !force) return;
        if (playing) pause();
        savePosition(true);
        Library.Entry e = Library.get(this, id);
        docId = id;
        title = e != null ? e.title : "";
        paras = Library.loadParagraphs(this, id);
        sentCache.clear();
        for (int i = 0; i < paras.size(); i++) sentCache.add(null);
        para = 0;
        sent = 0;
        if (e != null && e.para < paras.size()) {
            para = Math.max(0, e.para);
            sent = Math.max(0, Math.min(e.sentence, sentences(para).size() - 1));
        }
        updateMetadata();
        if (force) for (Listener l : copyListeners()) l.onDocumentChanged();
    }

    /** Lecture immédiate d'un document depuis un paragraphe (utilisé par le bouton flottant). */
    public void playFrom(String id, int p) {
        if (playing) pause();
        load(id, true);
        seek(p, 0);
        play();
    }

    public String docId() { return docId; }
    public List<String> paragraphs() { return paras; }
    public int para() { return para; }
    public int sentence() { return sent; }
    public boolean isPlaying() { return playing; }
    public boolean isTtsReady() { return ttsReady; }
    public TextToSpeech tts() { return tts; }

    public List<int[]> sentences(int p) {
        if (p < 0 || p >= paras.size()) return Collections.emptyList();
        List<int[]> s = sentCache.get(p);
        if (s == null) {
            s = Sentences.bounds(paras.get(p));
            sentCache.set(p, s);
        }
        return s;
    }

    // ------------------------------------------------------------------ commandes

    public void toggle() {
        if (playing) pause();
        else play();
    }

    public void play() {
        if (paras.isEmpty()) return;
        if (!ttsReady) {
            pendingPlay = true;
            if (ttsError != null) {
                for (Listener l : copyListeners()) l.onTtsReady(false, ttsError);
            }
            return;
        }
        if (!requestFocus()) return;
        // Document terminé : on repart du début.
        if (para >= paras.size()) { para = 0; sent = 0; }
        playing = true;
        pausedByFocus = false;
        if (!noisyRegistered) {
            registerReceiver(noisy, new IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY));
            noisyRegistered = true;
        }
        startForegroundCompat();
        speakFrom(para, sent);
        notifyState();
    }

    public void pause() {
        pendingPlay = false;
        if (!playing) return;
        playing = false;
        generation++;
        if (tts != null) tts.stop();
        if (noisyRegistered) {
            try { unregisterReceiver(noisy); } catch (Exception ignored) {}
            noisyRegistered = false;
        }
        if (!pausedByFocus) abandonFocus();
        savePosition(true);
        notifyState();
        stopForegroundCompat(false);
    }

    public void next() {
        if (paras.isEmpty()) return;
        int p = para, s = sent + 1;
        if (s >= sentences(p).size()) { p++; s = 0; }
        if (p >= paras.size()) return;
        seek(p, s);
    }

    public void previous() {
        if (paras.isEmpty()) return;
        int p = para, s = sent - 1;
        if (s < 0) {
            p--;
            if (p < 0) { p = 0; s = 0; }
            else s = Math.max(0, sentences(p).size() - 1);
        }
        seek(p, s);
    }

    public void nextParagraph() {
        if (para + 1 < paras.size()) seek(para + 1, 0);
    }

    public void previousParagraph() {
        // Comme un lecteur audio : un premier appui revient au début du paragraphe.
        if (sent > 0) seek(para, 0);
        else if (para > 0) seek(para - 1, 0);
    }

    public void seek(int p, int s) {
        if (paras.isEmpty()) return;
        p = Math.max(0, Math.min(p, paras.size() - 1));
        s = Math.max(0, Math.min(s, sentences(p).size() - 1));
        para = p;
        sent = s;
        if (playing) speakFrom(p, s);
        for (Listener l : copyListeners()) l.onPosition(para, sent);
        savePosition(false);
    }

    public void setRate(float r) {
        Prefs.setRate(this, r);
        if (tts != null) tts.setSpeechRate(r);
        if (playing) speakFrom(para, sent);
    }

    public void setPitch(float p) {
        Prefs.setPitch(this, p);
        if (tts != null) tts.setPitch(p);
        if (playing) speakFrom(para, sent);
    }

    public void setVoice(Voice v) {
        Prefs.setVoice(this, v == null ? "" : v.getName());
        if (tts == null) return;
        if (v == null) applyVoice(this, tts);
        else tts.setVoice(v);
        if (playing) speakFrom(para, sent);
    }

    /** Voix installées, françaises d'abord, puis triées par langue. */
    public List<Voice> voices() {
        List<Voice> out = new ArrayList<Voice>();
        if (tts == null || !ttsReady) return out;
        try {
            Set<Voice> set = tts.getVoices();
            if (set != null) out.addAll(set);
        } catch (Exception ignored) {
        }
        Collections.sort(out, new Comparator<Voice>() {
            @Override public int compare(Voice a, Voice b) {
                int fa = "fr".equals(a.getLocale().getLanguage()) ? 0 : 1;
                int fb = "fr".equals(b.getLocale().getLanguage()) ? 0 : 1;
                if (fa != fb) return fa - fb;
                int c = a.getLocale().toString().compareTo(b.getLocale().toString());
                if (c != 0) return c;
                return a.getName().compareTo(b.getName());
            }
        });
        return out;
    }

    /** Minuterie de sommeil : arrête la lecture après N minutes (0 = annuler). */
    public void setSleepTimer(int minutes) {
        main.removeCallbacks(sleepTask);
        if (minutes <= 0) { sleepAt = 0; return; }
        sleepAt = SystemClock.elapsedRealtime() + minutes * 60000L;
        main.postDelayed(sleepTask, minutes * 60000L);
    }

    public long sleepRemainingMs() {
        return sleepAt == 0 ? 0 : Math.max(0, sleepAt - SystemClock.elapsedRealtime());
    }

    // ------------------------------------------------------------------ moteur

    private void speakFrom(int p, int s) {
        generation++;
        tts.stop();
        qPara = p;
        qSent = s;
        queued = 0;
        fillQueue(true);
    }

    private void fillQueue(boolean first) {
        while (queued < LOOKAHEAD && qPara < paras.size()) {
            List<int[]> ss = sentences(qPara);
            if (qSent >= ss.size()) { qPara++; qSent = 0; continue; }
            int[] b = ss.get(qSent);
            String text = paras.get(qPara).substring(b[0], b[1]);
            String id = generation + ":" + qPara + ":" + qSent;
            Bundle params = new Bundle();
            tts.speak(text, first ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD, params, id);
            first = false;
            queued++;
            qSent++;
            if (qSent >= ss.size()) {
                qPara++;
                qSent = 0;
                // Petite pause entre deux paragraphes, comme une vraie lecture.
                if (qPara < paras.size()) tts.playSilentUtterance(350, TextToSpeech.QUEUE_ADD, "pause:" + generation);
            }
        }
    }

    private int[] parseId(String id) {
        String[] parts = id.split(":");
        if (parts.length != 3) return null;
        try {
            int g = Integer.parseInt(parts[0]);
            if (g != generation) return null;
            return new int[]{Integer.parseInt(parts[1]), Integer.parseInt(parts[2])};
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private void onUtteranceStart(String id) {
        int[] pos = parseId(id);
        if (pos == null || !playing) return;
        para = pos[0];
        sent = pos[1];
        for (Listener l : copyListeners()) l.onPosition(para, sent);
        savePosition(false);
    }

    private void onRange(String id, int start, int end) {
        int[] pos = parseId(id);
        if (pos == null || !playing) return;
        List<int[]> ss = sentences(pos[0]);
        if (pos[1] >= ss.size()) return;
        int base = ss.get(pos[1])[0];
        for (Listener l : copyListeners()) l.onWord(pos[0], base + start, base + end);
    }

    private void onUtteranceDone(String id) {
        int[] pos = parseId(id);
        if (pos == null || !playing) return;
        queued--;
        boolean last = pos[0] == paras.size() - 1 && pos[1] == sentences(pos[0]).size() - 1;
        if (last) {
            // Fin du document.
            playing = false;
            para = paras.size() - 1;
            sent = Math.max(0, sentences(para).size() - 1);
            abandonFocus();
            savePosition(true);
            notifyState();
            stopForegroundCompat(false);
            for (Listener l : copyListeners()) l.onFinished();
            return;
        }
        fillQueue(false);
    }

    private void savePosition(boolean force) {
        if (docId == null) return;
        long now = SystemClock.elapsedRealtime();
        if (!force && now - lastSave < 3000) return;
        lastSave = now;
        Library.savePosition(this, docId, para, sent);
    }

    // ------------------------------------------------------------------ focus audio

    private final AudioManager.OnAudioFocusChangeListener focusListener = new AudioManager.OnAudioFocusChangeListener() {
        @Override public void onAudioFocusChange(int change) {
            if (change == AudioManager.AUDIOFOCUS_LOSS) {
                pausedByFocus = false;
                pause();
            } else if (change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT
                    || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK) {
                // Appel, GPS, notification vocale : on met en pause et on reprend après.
                if (playing) {
                    pausedByFocus = true;
                    pause();
                }
            } else if (change == AudioManager.AUDIOFOCUS_GAIN) {
                if (pausedByFocus) {
                    pausedByFocus = false;
                    play();
                }
            }
        }
    };

    private boolean requestFocus() {
        if (focusRequest == null) {
            focusRequest = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                    .setAudioAttributes(new AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    .setWillPauseWhenDucked(true)
                    .setOnAudioFocusChangeListener(focusListener, main)
                    .build();
        }
        return audio.requestAudioFocus(focusRequest) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED;
    }

    private void abandonFocus() {
        if (focusRequest != null) audio.abandonAudioFocusRequest(focusRequest);
    }

    // ------------------------------------------------------------------ notification / session média

    private void notifyState() {
        for (Listener l : copyListeners()) l.onState(playing);
        long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE | PlaybackState.ACTION_PLAY_PAUSE
                | PlaybackState.ACTION_SKIP_TO_NEXT | PlaybackState.ACTION_SKIP_TO_PREVIOUS
                | PlaybackState.ACTION_STOP | PlaybackState.ACTION_FAST_FORWARD | PlaybackState.ACTION_REWIND;
        session.setPlaybackState(new PlaybackState.Builder()
                .setActions(actions)
                .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                        PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1f)
                .build());
        if (playing || docId != null) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            try {
                nm.notify(NOTIF_ID, buildNotification());
            } catch (SecurityException ignored) {
                // Notifications refusées : la lecture continue quand même.
            }
        }
    }

    private void updateMetadata() {
        session.setMetadata(new MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, "Lisys")
                .build());
    }

    private PendingIntent action(String a, int code) {
        Intent i = new Intent(this, ReaderService.class).setAction(a);
        return PendingIntent.getService(this, code, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private Notification buildNotification() {
        Intent open = new Intent(this, ReaderActivity.class).putExtra(ReaderActivity.EXTRA_ID, docId)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent content = PendingIntent.getActivity(this, 0, open,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification.Builder b = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_notif)
                .setContentTitle(title.length() > 0 ? title : "Lisys")
                .setContentText(playing ? "Lecture en cours" : "En pause")
                .setContentIntent(content)
                .setDeleteIntent(action(ACTION_STOP, 4))
                .setOngoing(playing)
                .setShowWhen(false)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setCategory(Notification.CATEGORY_TRANSPORT)
                .addAction(new Notification.Action.Builder(null, "Précédent", action(ACTION_PREV, 1)).build())
                .addAction(new Notification.Action.Builder(null, playing ? "Pause" : "Lire", action(ACTION_TOGGLE, 2)).build())
                .addAction(new Notification.Action.Builder(null, "Suivant", action(ACTION_NEXT, 3)).build())
                .setStyle(new Notification.MediaStyle()
                        .setMediaSession(session.getSessionToken())
                        .setShowActionsInCompactView(0, 1, 2));
        return b.build();
    }

    private void startForegroundCompat() {
        Notification n = buildNotification();
        try {
            // Le service doit être "démarré" pour survivre quand l'écran de lecture est fermé.
            startService(new Intent(this, ReaderService.class));
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK);
            } else {
                startForeground(NOTIF_ID, n);
            }
        } catch (Exception e) {
            // Android peut refuser depuis l'arrière-plan : la lecture continue sans premier plan.
        }
    }

    private void stopForegroundCompat(boolean remove) {
        stopForeground(remove ? Service.STOP_FOREGROUND_REMOVE : Service.STOP_FOREGROUND_DETACH);
    }
}
