package com.qmtech.telechargys

import android.app.DownloadManager
import android.content.Context
import android.content.Intent
import android.webkit.MimeTypeMap
import android.widget.Toast
import androidx.core.content.FileProvider
import java.io.File

/** Ouverture et partage des fichiers téléchargés. */
object Files {
    fun mimeOf(path: String): String {
        val ext = path.substringAfterLast('.', "").lowercase()
        return when (ext) {
            "apk" -> "application/vnd.android.package-archive"
            "m3u8" -> "application/vnd.apple.mpegurl"
            "mkv" -> "video/x-matroska"
            "ts" -> "video/mp2t"
            "flac" -> "audio/flac"
            "opus" -> "audio/ogg"
            else -> MimeTypeMap.getSingleton().getMimeTypeFromExtension(ext) ?: "*/*"
        }
    }

    private fun uri(ctx: Context, path: String) = FileProvider.getUriForFile(ctx, ctx.packageName + ".files", File(path))

    fun viewIntent(ctx: Context, path: String): Intent? = runCatching {
        Intent(Intent.ACTION_VIEW).setDataAndType(uri(ctx, path), mimeOf(path))
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
    }.getOrNull()

    fun open(ctx: Context, path: String) {
        if (!File(path).exists()) { toast(ctx, "Fichier introuvable (déplacé ou supprimé)"); return }
        val i = viewIntent(ctx, path)
        if (i == null) { toast(ctx, "Impossible d'ouvrir ce fichier"); return }
        runCatching { ctx.startActivity(i) }.onFailure { toast(ctx, "Aucune application pour ouvrir ce type de fichier") }
    }

    fun share(ctx: Context, path: String) {
        if (!File(path).exists()) { toast(ctx, "Fichier introuvable (déplacé ou supprimé)"); return }
        runCatching {
            val i = Intent(Intent.ACTION_SEND).setType(mimeOf(path)).putExtra(Intent.EXTRA_STREAM, uri(ctx, path))
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            ctx.startActivity(Intent.createChooser(i, "Partager").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }.onFailure { toast(ctx, "Partage impossible") }
    }

    fun openDownloads(ctx: Context) {
        runCatching { ctx.startActivity(Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) }
            .onFailure { toast(ctx, "Dossier : Téléchargements/Telechargys") }
    }

    fun toast(ctx: Context, msg: String) = Toast.makeText(ctx, msg, Toast.LENGTH_SHORT).show()
}
