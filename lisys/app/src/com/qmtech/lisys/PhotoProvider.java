package com.qmtech.lisys;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Donne à l'appli Appareil photo un endroit où enregistrer la photo à lire
 * (cache/photos/photo.jpg). Remplace FileProvider, sans bibliothèque externe.
 */
public class PhotoProvider extends ContentProvider {

    static final String AUTHORITY = "com.qmtech.lisys.photos";

    static Uri photoUri() {
        return Uri.parse("content://" + AUTHORITY + "/photo.jpg");
    }

    static File photoFile(android.content.Context c) {
        File d = new File(c.getCacheDir(), "photos");
        d.mkdirs();
        return new File(d, "photo.jpg");
    }

    @Override public boolean onCreate() { return true; }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (!"photo.jpg".equals(uri.getLastPathSegment())) throw new FileNotFoundException(uri.toString());
        File f = photoFile(getContext());
        int m = ParcelFileDescriptor.parseMode(mode);
        if ((m & ParcelFileDescriptor.MODE_WRITE_ONLY) != 0 || (m & ParcelFileDescriptor.MODE_READ_WRITE) != 0) {
            m |= ParcelFileDescriptor.MODE_CREATE;
        }
        return ParcelFileDescriptor.open(f, m);
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String sel, String[] args, String sort) {
        File f = photoFile(getContext());
        MatrixCursor c = new MatrixCursor(new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE});
        c.addRow(new Object[]{"photo.jpg", f.length()});
        return c;
    }

    @Override public String getType(Uri uri) { return "image/jpeg"; }
    @Override public Uri insert(Uri uri, ContentValues v) { return null; }
    @Override public int delete(Uri uri, String s, String[] a) { return 0; }
    @Override public int update(Uri uri, ContentValues v, String s, String[] a) { return 0; }
}
