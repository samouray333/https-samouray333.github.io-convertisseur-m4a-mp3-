package fr.qmtech.transferys

import android.Manifest
import android.app.Activity
import android.app.DownloadManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.database.Cursor
import android.media.MediaScannerConnection
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.os.PowerManager
import android.os.StatFs
import android.provider.DocumentsContract
import android.provider.MediaStore
import android.provider.OpenableColumns
import android.provider.Settings
import android.webkit.MimeTypeMap
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.concurrent.Executors

/**
 * Pont natif de Transferys : sélecteurs de fichiers (sans copie : on lit les
 * contenus via leur descripteur), menu Partager, permissions, service au
 * premier plan, espace disque, galerie, verrou multicast Wi-Fi.
 */
class MainActivity : FlutterActivity() {
    private val channelName = "fr.qmtech.transferys/native"
    private var channel: MethodChannel? = null
    private var pendingResult: MethodChannel.Result? = null
    private var pendingPermission: MethodChannel.Result? = null
    private var initialShare: List<Map<String, Any?>> = emptyList()
    private var multicastLock: WifiManager.MulticastLock? = null
    private val io = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())

    companion object {
        const val REQ_FILES = 4101
        const val REQ_MEDIA = 4102
        const val REQ_FOLDER = 4103
        const val REQ_DIR = 4104
        const val REQ_PERM = 4201
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        initialShare = sharedItems(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val items = sharedItems(intent)
        if (items.isNotEmpty()) channel?.invokeMethod("onShare", items)
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val ch = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
        channel = ch
        ch.setMethodCallHandler { call, result ->
            try {
                handle(call, result)
            } catch (e: Exception) {
                result.error("native", e.message, null)
            }
        }
    }

    private fun handle(call: MethodCall, result: MethodChannel.Result) {
        when (call.method) {
            "deviceModel" -> {
                val name = try { Settings.Global.getString(contentResolver, "device_name") } catch (_: Exception) { null }
                result.success(if (!name.isNullOrBlank()) name else Build.MODEL)
            }
            "sdkInt" -> result.success(Build.VERSION.SDK_INT)
            "downloadsDir" -> result.success(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).absolutePath
            )
            "initialShare" -> {
                result.success(initialShare)
                initialShare = emptyList()
            }
            "pickFiles" -> {
                val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "*/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
                startPicker(i, REQ_FILES, result)
            }
            "pickMedia" -> {
                val i = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                    Intent(MediaStore.ACTION_PICK_IMAGES).apply {
                        putExtra(MediaStore.EXTRA_PICK_IMAGES_MAX, MediaStore.getPickImagesMaxLimit())
                    }
                } else {
                    Intent(Intent.ACTION_GET_CONTENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                        putExtra(Intent.EXTRA_MIME_TYPES, arrayOf("image/*", "video/*"))
                        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    }
                }
                startPicker(i, REQ_MEDIA, result)
            }
            "pickFolder" -> startPicker(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_FOLDER, result)
            "pickDirectory" -> startPicker(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE), REQ_DIR, result)
            "openFd" -> {
                val uri = Uri.parse(call.argument<String>("uri"))
                val pfd = contentResolver.openFileDescriptor(uri, "r")
                result.success(pfd?.detachFd() ?: -1)
            }
            "closeFd" -> {
                val fd = call.argument<Int>("fd") ?: -1
                if (fd >= 0) try { ParcelFileDescriptor.adoptFd(fd).close() } catch (_: Exception) {}
                result.success(null)
            }
            "freeSpace" -> {
                var f = File(call.argument<String>("path") ?: "/")
                while (!f.exists() && f.parentFile != null) f = f.parentFile!!
                result.success(StatFs(f.absolutePath).availableBytes)
            }
            "scanFile" -> {
                val p = call.argument<String>("path")
                if (p != null) MediaScannerConnection.scanFile(applicationContext, arrayOf(p), null, null)
                result.success(null)
            }
            "openFile" -> result.success(openFile(call.argument<String>("path")!!))
            "shareFile" -> result.success(shareFile(call.argument<String>("path")!!))
            "openFolder" -> result.success(openFolder(call.argument<String>("path")!!))
            "acquireLocks" -> {
                if (multicastLock == null) {
                    val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                    multicastLock = wm.createMulticastLock("transferys-discovery").apply {
                        setReferenceCounted(false)
                        acquire()
                    }
                }
                result.success(null)
            }
            "service" -> {
                val active = call.argument<Boolean>("active") ?: false
                val i = Intent(this, TransferService::class.java)
                if (active) {
                    i.action = TransferService.ACTION_UPDATE
                    i.putExtra("title", call.argument<String>("title"))
                    i.putExtra("text", call.argument<String>("text"))
                    i.putExtra("percent", call.argument<Int>("percent") ?: -1)
                    try {
                        ContextCompat.startForegroundService(this, i)
                    } catch (_: Exception) {
                        // Démarrage refusé en arrière-plan (Android 12+) : le
                        // transfert continue tant que le système garde l'appli.
                    }
                } else if (TransferService.running) {
                    i.action = TransferService.ACTION_STOP
                    try { startService(i) } catch (_: Exception) {}
                }
                result.success(null)
            }
            "requestNotifications" -> {
                if (Build.VERSION.SDK_INT >= 33 &&
                    ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                ) {
                    pendingPermission = result
                    requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_PERM)
                } else result.success(true)
            }
            "requestLegacyStorage" -> {
                if (Build.VERSION.SDK_INT < 30 &&
                    ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
                ) {
                    pendingPermission = result
                    requestPermissions(
                        arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE, Manifest.permission.READ_EXTERNAL_STORAGE),
                        REQ_PERM
                    )
                } else result.success(true)
            }
            "hasAllFilesAccess" -> result.success(
                if (Build.VERSION.SDK_INT >= 30) Environment.isExternalStorageManager() else true
            )
            "requestAllFilesAccess" -> {
                if (Build.VERSION.SDK_INT >= 30) {
                    try {
                        startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:$packageName")))
                    } catch (_: Exception) {
                        startActivity(Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION))
                    }
                }
                result.success(null)
            }
            "ignoringBattery" -> {
                val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
                result.success(pm.isIgnoringBatteryOptimizations(packageName))
            }
            "requestIgnoreBattery" -> {
                try {
                    startActivity(Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:$packageName")))
                } catch (_: Exception) {
                    try { startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)) } catch (_: Exception) {}
                }
                result.success(null)
            }
            else -> result.notImplemented()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_PERM) {
            pendingPermission?.success(grantResults.isNotEmpty() && grantResults.all { it == PackageManager.PERMISSION_GRANTED })
            pendingPermission = null
        }
    }

    // ------------------------------------------------------------ sélecteurs
    private fun startPicker(i: Intent, code: Int, result: MethodChannel.Result) {
        pendingResult?.success(if (code == REQ_DIR) null else emptyList<Any>())
        pendingResult = result
        try {
            startActivityForResult(i, code)
        } catch (e: ActivityNotFoundException) {
            pendingResult = null
            result.error("no_picker", "Aucun sélecteur de fichiers disponible", null)
        }
    }

    @Deprecated("API Activity classique, suffisante ici")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val res = pendingResult ?: return
        if (requestCode !in listOf(REQ_FILES, REQ_MEDIA, REQ_FOLDER, REQ_DIR)) return
        pendingResult = null
        if (resultCode != Activity.RESULT_OK || data == null) {
            res.success(if (requestCode == REQ_DIR) null else emptyList<Any>())
            return
        }
        when (requestCode) {
            REQ_FILES, REQ_MEDIA -> {
                val uris = mutableListOf<Uri>()
                data.clipData?.let { cd -> for (k in 0 until cd.itemCount) uris.add(cd.getItemAt(k).uri) }
                if (uris.isEmpty()) data.data?.let { uris.add(it) }
                io.execute {
                    val out = uris.mapNotNull { describe(it, null) }
                    main.post { res.success(out) }
                }
            }
            REQ_FOLDER -> {
                val tree = data.data!!
                try {
                    contentResolver.takePersistableUriPermission(tree, Intent.FLAG_GRANT_READ_URI_PERMISSION)
                } catch (_: Exception) {}
                io.execute {
                    val out = mutableListOf<Map<String, Any?>>()
                    try {
                        val rootId = DocumentsContract.getTreeDocumentId(tree)
                        val rootName = queryName(DocumentsContract.buildDocumentUriUsingTree(tree, rootId)) ?: "Dossier"
                        walkTree(tree, rootId, rootName, out)
                    } catch (_: Exception) {}
                    main.post { res.success(out) }
                }
            }
            REQ_DIR -> res.success(treeToPath(data.data!!))
        }
    }

    /** Parcours rapide d'une arborescence SAF (requêtes DocumentsContract). */
    private fun walkTree(tree: Uri, docId: String, prefix: String, out: MutableList<Map<String, Any?>>) {
        val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, docId)
        val cols = arrayOf(
            DocumentsContract.Document.COLUMN_DOCUMENT_ID,
            DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            DocumentsContract.Document.COLUMN_MIME_TYPE,
            DocumentsContract.Document.COLUMN_SIZE,
            DocumentsContract.Document.COLUMN_LAST_MODIFIED
        )
        val dirs = mutableListOf<Pair<String, String>>()
        contentResolver.query(children, cols, null, null, null)?.use { c ->
            while (c.moveToNext()) {
                val id = c.getString(0)
                val name = c.getString(1) ?: "fichier"
                val mime = c.getString(2)
                if (mime == DocumentsContract.Document.MIME_TYPE_DIR) {
                    dirs.add(id to "$prefix/$name")
                } else {
                    out.add(
                        mapOf(
                            "uri" to DocumentsContract.buildDocumentUriUsingTree(tree, id).toString(),
                            "name" to name,
                            "relPath" to "$prefix/$name",
                            "size" to (if (c.isNull(3)) 0L else c.getLong(3)),
                            "modified" to (if (c.isNull(4)) System.currentTimeMillis() else c.getLong(4))
                        )
                    )
                }
            }
        }
        for ((id, p) in dirs) walkTree(tree, id, p, out)
    }

    private fun queryName(uri: Uri): String? = try {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }
    } catch (_: Exception) { null }

    /** Nom, taille et date d'un contenu (content:// ou file://). */
    private fun describe(uri: Uri, relPath: String?): Map<String, Any?>? {
        return try {
            var name: String? = null
            var size = -1L
            var modified = System.currentTimeMillis()
            contentResolver.query(uri, null, null, null, null)?.use { c: Cursor ->
                if (c.moveToFirst()) {
                    val ni = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    val si = c.getColumnIndex(OpenableColumns.SIZE)
                    val mi = c.getColumnIndex(DocumentsContract.Document.COLUMN_LAST_MODIFIED)
                    if (ni >= 0) name = c.getString(ni)
                    if (si >= 0 && !c.isNull(si)) size = c.getLong(si)
                    if (mi >= 0 && !c.isNull(mi)) modified = c.getLong(mi)
                }
            }
            if (size < 0) {
                contentResolver.openFileDescriptor(uri, "r")?.use { size = it.statSize }
            }
            if (name == null) name = uri.lastPathSegment?.substringAfterLast('/') ?: "fichier"
            mapOf("uri" to uri.toString(), "name" to name, "relPath" to (relPath ?: name), "size" to size, "modified" to modified)
        } catch (_: Exception) {
            null
        }
    }

    private fun sharedItems(intent: Intent?): List<Map<String, Any?>> {
        if (intent == null) return emptyList()
        val uris = mutableListOf<Uri>()
        when (intent.action) {
            Intent.ACTION_SEND -> {
                @Suppress("DEPRECATION")
                (intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))?.let { uris.add(it) }
            }
            Intent.ACTION_SEND_MULTIPLE -> {
                @Suppress("DEPRECATION")
                intent.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.let { uris.addAll(it) }
            }
            else -> return emptyList()
        }
        if (uris.isEmpty()) intent.clipData?.let { cd -> for (k in 0 until cd.itemCount) cd.getItemAt(k).uri?.let { uris.add(it) } }
        // Partage de texte seul (lien…) : enregistré dans un petit fichier .txt.
        if (uris.isEmpty()) {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return emptyList()
            val f = File(cacheDir, "Texte partagé ${System.currentTimeMillis() / 1000}.txt")
            f.writeText(text)
            return listOfNotNull(describe(Uri.fromFile(f), null))
        }
        return uris.mapNotNull { describe(it, null) }
    }

    /** content://…/tree/primary:Download/X → /storage/emulated/0/Download/X */
    private fun treeToPath(tree: Uri): String? {
        return try {
            val id = DocumentsContract.getTreeDocumentId(tree)
            val parts = id.split(":", limit = 2)
            val rel = if (parts.size > 1) parts[1] else ""
            val base = if (parts[0].equals("primary", true)) Environment.getExternalStorageDirectory().absolutePath else "/storage/${parts[0]}"
            if (rel.isEmpty()) base else "$base/$rel"
        } catch (_: Exception) { null }
    }

    // --------------------------------------------------------- ouverture
    private fun mimeOf(f: File): String =
        MimeTypeMap.getSingleton().getMimeTypeFromExtension(f.extension.lowercase()) ?: "*/*"

    private fun uriFor(f: File): Uri = FileProvider.getUriForFile(this, "$packageName.files", f)

    private fun openFile(path: String): Boolean = try {
        val f = File(path)
        val i = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uriFor(f), mimeOf(f))
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(Intent.createChooser(i, "Ouvrir avec").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (_: Exception) { false }

    private fun shareFile(path: String): Boolean = try {
        val f = File(path)
        val i = Intent(Intent.ACTION_SEND).apply {
            type = mimeOf(f)
            putExtra(Intent.EXTRA_STREAM, uriFor(f))
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        startActivity(Intent.createChooser(i, "Partager").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        true
    } catch (_: Exception) { false }

    private fun openFolder(path: String): Boolean {
        // Ouvre l'appli Fichiers sur le dossier (si le fabricant le permet),
        // sinon sur les Téléchargements.
        val root = Environment.getExternalStorageDirectory().absolutePath
        if (path.startsWith(root)) {
            val rel = path.removePrefix(root).trimStart('/')
            val uri = DocumentsContract.buildDocumentUri("com.android.externalstorage.documents", "primary:$rel")
            for (type in listOf(DocumentsContract.Document.MIME_TYPE_DIR, "resource/folder")) {
                try {
                    startActivity(Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(uri, type)
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
                    })
                    return true
                } catch (_: Exception) {}
            }
        }
        return try {
            startActivity(Intent(DownloadManager.ACTION_VIEW_DOWNLOADS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            true
        } catch (_: Exception) { false }
    }
}
