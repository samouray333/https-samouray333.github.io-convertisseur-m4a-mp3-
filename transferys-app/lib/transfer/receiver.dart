// Réception des fichiers : fichiers partiels (.part) dans un dossier caché,
// reprise après coupure (même après redémarrage de l'appli), SHA-256 calculé
// au fil de l'eau, gestion des doublons à la finalisation.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

import '../core/errors.dart';
import '../core/models.dart';
import 'file_utils.dart';
import 'hasher.dart';
import 'job.dart';

const String partialDirName = '.transferys-partial';


class IncomingFileInfo {
  IncomingFileInfo({required this.fileId, required this.relPath, required this.size, required this.modified});
  final String fileId;
  final String relPath;
  final int size;
  final DateTime? modified;

  factory IncomingFileInfo.fromJson(Map<String, dynamic> j) => IncomingFileInfo(
        fileId: j['fileId'].toString(),
        relPath: (j['relPath'] as String?) ?? 'fichier',
        size: (j['size'] as num).toInt(),
        modified: j['modified'] is num ? DateTime.fromMillisecondsSinceEpoch((j['modified'] as num).toInt()) : null,
      );
}

/// Demande de réception présentée à l'utilisateur.
class IncomingRequest {
  IncomingRequest({required this.sessionId, required this.from, required this.files});
  final String sessionId;
  final TrustedDevice from;
  final List<IncomingFileInfo> files;
  int get totalSize => files.fold(0, (a, f) => a + f.size);
}

class ReceiveFile {
  ReceiveFile(this.info, this.view);
  final IncomingFileInfo info;
  final TransferFile view;
  bool skip = false;
  late String partPath;
  late String targetPath; // chemin prévu (avant gestion des doublons)
  int offset = 0;
  RandomAccessFile? _raf;
  StreamingHasher? _hasher;
  bool done = false;
  Future<void> _lock = Future.value();

  /// Exécute [f] en exclusion mutuelle sur ce fichier.
  Future<T> locked<T>(Future<T> Function() f) {
    final c = Completer<T>();
    final prev = _lock;
    _lock = c.future.then((_) {}, onError: (_) {});
    prev.whenComplete(() async {
      try {
        c.complete(await f());
      } catch (e, st) {
        c.completeError(e, st);
      }
    });
    return c.future;
  }

  /// Ouvre le .part et recalcule le SHA-256 des octets déjà présents.
  Future<void> ensureOpen() async {
    if (_raf != null) return;
    final f = File(partPath);
    await f.parent.create(recursive: true);
    final raf = await f.open(mode: FileMode.append);
    _hasher?.dispose();
    _hasher = await StreamingHasher.create(info.size);
    final len = await raf.length();
    if (len > 0) {
      await raf.setPosition(0);
      var read = 0;
      while (read < len) {
        final buf = await raf.read(len - read > 4 << 20 ? 4 << 20 : len - read);
        if (buf.isEmpty) break;
        await _hasher!.add(buf);
        read += buf.length;
      }
      await raf.setPosition(len);
    }
    offset = len;
    _raf = raf;
  }

  Future<void> write(Uint8List data) async {
    // Écriture disque et hachage en parallèle.
    await Future.wait([_raf!.writeFrom(data), _hasher!.add(data)]);
    offset += data.length;
  }

  /// Termine le hachage et ferme le fichier ; renvoie le SHA-256 hexadécimal.
  Future<String> closeAndDigest() async {
    await _raf?.flush();
    await _raf?.close();
    _raf = null;
    final h = _hasher;
    _hasher = null;
    return h == null ? sha256.convert(const []).toString() : await h.close();
  }

  Future<void> closeQuietly() async {
    try {
      await _raf?.close();
    } catch (_) {}
    _raf = null;
    _hasher?.dispose();
    _hasher = null;
  }

  Future<void> discardPart() async {
    await closeQuietly();
    try {
      await File(partPath).delete();
    } catch (_) {}
    try {
      await File('$partPath.json').delete();
    } catch (_) {}
    offset = 0;
  }
}

class ReceiveSession {
  ReceiveSession({required this.id, required this.from, required this.job, required this.receiveDir});
  final String id;
  final TrustedDevice from;
  final TransferJob job;
  final String receiveDir;
  final files = <String, ReceiveFile>{};
  bool accepted = false;
  bool cancelled = false;
  bool pausedByReceiver = false;
  bool finished = false;

  /// Échec définitif (ex. disque plein) renvoyé aux requêtes suivantes.
  (int, Map<String, Object?>)? failure;
  DateTime lastActivity = DateTime.now();

  /// Réponse mémorisée (la demande peut être renvoyée après une coupure).
  Map<String, dynamic>? acceptResponse;
  Future<Map<String, dynamic>>? pendingDecision;

  String get partialDir => p.join(receiveDir, partialDirName);

  /// Clé stable d'un fichier partiel : même appareil + même chemin + même
  /// taille + même date = on reprend là où on en était.
  static String partKey(String deviceId, IncomingFileInfo f) => sha256
      .convert(utf8.encode('$deviceId|${f.relPath}|${f.size}|${f.modified?.millisecondsSinceEpoch ?? 0}'))
      .toString()
      .substring(0, 32);

  /// Prépare les fichiers : chemins cibles, doublons « ignorer », reprise.
  Future<void> prepare(DuplicateMode mode) async {
    for (final rf in files.values) {
      final parts = sanitizeRelPath(rf.info.relPath);
      rf.targetPath = p.joinAll([receiveDir, ...parts]);
      rf.partPath = p.join(partialDir, '${partKey(from.id, rf.info)}.part');
      if (mode == DuplicateMode.skip && await File(rf.targetPath).exists()) {
        rf.skip = true;
        rf.view.status = TransferStatus.skipped;
        rf.view.savedPath = rf.targetPath;
        continue;
      }
      final part = File(rf.partPath);
      if (await part.exists()) {
        final len = await part.length();
        if (len <= rf.info.size) {
          rf.offset = len;
        } else {
          await part.delete();
          rf.offset = 0;
        }
      }
      rf.view.transferred = rf.offset;
    }
  }

  /// Octets restant réellement à écrire (pour le contrôle d'espace disque).
  int get bytesNeeded => files.values.where((f) => !f.skip).fold(0, (a, f) => a + (f.info.size - f.offset));

  /// Finalise un fichier complet : renomme le .part vers sa destination selon
  /// la gestion des doublons, restaure la date de modification.
  Future<String> finalizeFile(ReceiveFile rf, DuplicateMode mode) async {
    var dest = rf.targetPath;
    if (await File(dest).exists()) {
      switch (mode) {
        case DuplicateMode.replace:
          try {
            await File(dest).delete();
          } catch (_) {
            dest = uniquePath(dest); // fichier verrouillé : on renomme plutôt
          }
          break;
        case DuplicateMode.rename:
        case DuplicateMode.skip: // apparu pendant le transfert : on renomme
          dest = uniquePath(dest);
          break;
      }
    }
    final f = await moveFile(File(rf.partPath), dest);
    if (rf.info.modified != null) {
      try {
        await f.setLastModified(rf.info.modified!);
      } catch (_) {}
    }
    try {
      await File('${rf.partPath}.json').delete();
    } catch (_) {}
    rf.done = true;
    return f.path;
  }

  Future<void> closeAll({bool deleteParts = false}) async {
    for (final rf in files.values) {
      if (deleteParts && !rf.done) {
        await rf.discardPart();
      } else {
        await rf.closeQuietly();
      }
    }
    await cleanupPartialDir();
  }

  Future<void> cleanupPartialDir() async {
    try {
      final d = Directory(partialDir);
      if (await d.exists() && await d.list().isEmpty) await d.delete();
    } catch (_) {}
  }
}

/// Supprime les fichiers partiels abandonnés depuis plus de [maxAge].
Future<void> purgeOldPartials(String receiveDir, {Duration maxAge = const Duration(days: 7)}) async {
  final d = Directory(p.join(receiveDir, partialDirName));
  if (!await d.exists()) return;
  final now = DateTime.now();
  await for (final e in d.list()) {
    try {
      if (e is File && now.difference(await e.lastModified()) > maxAge) await e.delete();
    } catch (_) {}
  }
  try {
    if (await d.list().isEmpty) await d.delete();
  } catch (_) {}
}

/// Erreur d'écriture → réponse HTTP adaptée.
(int, Map<String, Object?>) writeErrorResponse(Object e) {
  if (isDiskFull(e)) return (507, {'error': 'disk_full'});
  if (e is FileSystemException) return (500, {'error': 'write_failed', 'message': e.message});
  return (500, {'error': 'internal', 'message': '$e'});
}
