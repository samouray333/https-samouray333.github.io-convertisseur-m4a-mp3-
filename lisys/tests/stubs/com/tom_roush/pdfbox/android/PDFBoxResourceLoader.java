package com.tom_roush.pdfbox.android;

import java.io.IOException;
import java.io.InputStream;

/** Remplace le chargeur d'assets Android pour les tests sur PC (lit les assets depuis le classpath). */
public class PDFBoxResourceLoader {
    public static void init(android.content.Context c) {}
    public static boolean isReady() { return true; }
    public static InputStream getStream(String path) throws IOException {
        InputStream in = PDFBoxResourceLoader.class.getClassLoader().getResourceAsStream(path);
        if (in == null) throw new IOException("asset introuvable : " + path);
        return in;
    }
}
