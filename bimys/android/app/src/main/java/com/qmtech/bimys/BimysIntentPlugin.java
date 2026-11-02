package com.qmtech.bimys;

import android.app.Activity;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.provider.OpenableColumns;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Réception d'un fichier IFC ouvert depuis le gestionnaire de fichiers (« Ouvrir avec ») ou partagé vers Bimys.
 * Le fichier est copié dans le cache de l'application puis lu par la partie web.
 */
@CapacitorPlugin(name = "BimysIntent")
public class BimysIntentPlugin extends Plugin {
    private static BimysIntentPlugin instance;
    private static String pendingPath;
    private static String pendingName;
    private static boolean copying = false;
    private static PluginCall waiting;

    @Override
    public void load() {
        instance = this;
    }

    public static void handleIntent(Activity activity, Intent intent, boolean notify) {
        if (intent == null) return;
        String action = intent.getAction();
        Uri uri = null;
        if (Intent.ACTION_VIEW.equals(action)) uri = intent.getData();
        else if (Intent.ACTION_SEND.equals(action)) uri = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        if (uri == null) return;
        final Uri src = uri;
        copying = true;
        new Thread(() -> {
            String name = displayName(activity, src);
            String path = null;
            try {
                File dir = new File(activity.getCacheDir(), "incoming");
                if (!dir.exists()) dir.mkdirs();
                File[] old = dir.listFiles();
                if (old != null) for (File f : old) f.delete();
                File out = new File(dir, name.replaceAll("[^A-Za-z0-9._ -]", "_"));
                try (InputStream in = activity.getContentResolver().openInputStream(src); OutputStream os = new FileOutputStream(out)) {
                    byte[] buf = new byte[1 << 16];
                    int n;
                    while (in != null && (n = in.read(buf)) > 0) os.write(buf, 0, n);
                }
                path = out.getAbsolutePath();
            } catch (Exception e) {
                path = null;
            }
            synchronized (BimysIntentPlugin.class) {
                copying = false;
                if (path == null) {
                    if (waiting != null) {
                        waiting.resolve(new JSObject());
                        waiting = null;
                    }
                    return;
                }
                if (waiting != null) {
                    JSObject r = new JSObject();
                    r.put("path", path);
                    r.put("name", name);
                    waiting.resolve(r);
                    waiting = null;
                } else if (notify && instance != null) {
                    JSObject d = new JSObject();
                    d.put("path", path);
                    d.put("name", name);
                    instance.notifyListeners("fileOpened", d, true);
                } else {
                    pendingPath = path;
                    pendingName = name;
                }
            }
        }).start();
    }

    private static String displayName(Activity a, Uri uri) {
        String name = null;
        try (Cursor c = a.getContentResolver().query(uri, new String[] { OpenableColumns.DISPLAY_NAME }, null, null, null)) {
            if (c != null && c.moveToFirst()) name = c.getString(0);
        } catch (Exception ignored) {
        }
        if (name == null) name = uri.getLastPathSegment();
        if (name == null || name.isEmpty()) name = "maquette.ifc";
        return name;
    }

    @PluginMethod
    public void getPendingFile(PluginCall call) {
        synchronized (BimysIntentPlugin.class) {
            if (pendingPath != null) {
                JSObject r = new JSObject();
                r.put("path", pendingPath);
                r.put("name", pendingName);
                pendingPath = null;
                pendingName = null;
                call.resolve(r);
            } else if (copying) {
                call.setKeepAlive(false);
                waiting = call;
            } else {
                call.resolve(new JSObject());
            }
        }
    }
}
