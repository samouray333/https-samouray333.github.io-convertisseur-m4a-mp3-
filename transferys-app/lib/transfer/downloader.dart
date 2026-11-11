// Téléchargement de fichiers depuis un autre appareil (explorateur distant
// ou fichiers proposés par le PC à un téléphone en 4G).
// Même robustesse que l'envoi : morceaux de 8 Mo, reprise après coupure (et
// après redémarrage via le fichier partiel), SHA-256 vérifié à la fin.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

import '../core/errors.dart';
import '../core/models.dart';
import 'client.dart';
import 'file_utils.dart';
import 'hasher.dart';
import 'job.dart';
import 'protocol.dart';
import 'receiver.dart' show partialDirName;

class RemoteFile {
  RemoteFile({required this.fileId, required this.relPath, required this.size, this.modified, required this.query});
  final String fileId;

  /// Chemin relatif local (sous-dossiers conservés).
  final String relPath;
  final int size;
  final DateTime? modified;

  /// Paramètres d'accès : {share, path} ou {offer, file}.
  final Map<String, String> query;
}

class DownloadJob {
  DownloadJob({
    required this.job,
    required this.files,
    required this.destDir,
    required this.peerId,
    required this.createClient,
    required this.resolveAddress,
    required this.duplicateMode,
    this.onFileSaved,
    this.onFileDone,
    this.reconnectWindow = const Duration(minutes: 10),
  });

  final TransferJob job;
  final List<RemoteFile> files;
  final String destDir;
  final String peerId;
  final PeerClient Function(String host) createClient;
  final Future<String?> Function() resolveAddress;
  final DuplicateMode duplicateMode;
  final Future<void> Function(String path)? onFileSaved;

  /// Rapport par fichier (offres : prévient l'appareil source).
  final Future<void> Function(RemoteFile f, bool ok, String? error, bool finished)? onFileDone;
  final Duration reconnectWindow;

  PeerClient? _client;
  String? _host;
  bool _paused = false;
  bool _cancelled = false;
  HttpClientRequest? _req;

  Future<void> run() async {
    job.onPause = () {
      _paused = true;
      job.status = TransferStatus.paused;
      job.notify(force: true);
    };
    job.onResume = () {
      _paused = false;
      job.status = TransferStatus.running;
      job.speed.reset();
      job.notify(force: true);
    };
    job.onCancel = () {
      _cancelled = true;
      try {
        _req?.abort();
      } catch (_) {}
      job.status = TransferStatus.cancelled;
      job.notify(force: true);
    };
    try {
      _host = await resolveAddress();
      if (_host == null) throw TransferysException(ErrorCode.unreachable, '${job.peerName} est injoignable.');
      _client = createClient(_host!);
      job.status = TransferStatus.running;
      job.notify(force: true);
      for (var i = 0; i < files.length; i++) {
        if (_cancelled) break;
        final ok = await _one(files[i], job.files[i]);
        final last = i == files.length - 1;
        await onFileDone?.call(files[i], ok, job.files[i].error, last).catchError((_) {});
      }
      if (!_cancelled) {
        job.status = job.failedCount > 0 ? TransferStatus.failed : TransferStatus.done;
        if (job.status == TransferStatus.failed) {
          final first = job.files.map((f) => f.error).whereType<String>().firstOrNull;
          job.error = '${job.failedCount} fichier(s) non téléchargé(s).${first != null ? ' Raison : $first' : ''}';
        }
      }
    } catch (e) {
      if (!_cancelled) {
        job.status = TransferStatus.failed;
        job.error = e is TransferysException ? e.message : describeNetworkError(e, peerName: job.peerName).message;
      }
    } finally {
      if (_cancelled) {
        job.status = TransferStatus.cancelled;
        job.error ??= 'Téléchargement annulé.';
        if (onFileDone != null && files.isNotEmpty) {
          await onFileDone!(files.last, false, 'Annulé', true).catchError((_) {});
        }
      }
      for (final f in job.files) {
        if (!f.status.isFinal) f.status = _cancelled ? TransferStatus.cancelled : TransferStatus.failed;
      }
      job.notify(force: true);
      _client?.close();
      try {
        final d = Directory(p.join(destDir, partialDirName));
        if (await d.exists() && await d.list().isEmpty) await d.delete();
      } catch (_) {}
    }
  }

  Future<T> _net<T>(Future<T> Function() action, TransferFile f) async {
    DateTime? lost;
    var attempt = 0;
    while (true) {
      if (_cancelled) throw TransferysException(ErrorCode.unknown, 'Annulé');
      try {
        final r = await action();
        if (lost != null) {
          job.status = _paused ? TransferStatus.paused : TransferStatus.running;
          job.error = null;
          f.status = TransferStatus.running;
          job.notify(force: true);
        }
        return r;
      } catch (e) {
        if (_cancelled) rethrow;
        if (e is TransferysException && e.code == ErrorCode.certificateChanged) rethrow;
        if (!isNetworkError(e)) rethrow;
        lost ??= DateTime.now();
        if (DateTime.now().difference(lost) > reconnectWindow) {
          throw TransferysException(ErrorCode.unreachable, 'Connexion perdue avec ${job.peerName} depuis plus de 10 minutes.');
        }
        job.status = TransferStatus.reconnecting;
        job.error = 'Connexion perdue, nouvelle tentative…';
        f.status = TransferStatus.reconnecting;
        job.speed.reset();
        job.notify(force: true);
        const delays = [1, 2, 3, 5, 8, 10];
        await Future.delayed(Duration(seconds: delays[attempt < delays.length ? attempt : delays.length - 1]));
        attempt++;
        final h = await resolveAddress();
        if (h != null) _host = h;
        _client?.close();
        _client = createClient(_host!);
      }
    }
  }

  Future<bool> _one(RemoteFile rf, TransferFile f) async {
    f.status = TransferStatus.running;
    final parts = sanitizeRelPath(rf.relPath);
    final target = p.joinAll([destDir, ...parts]);
    if (duplicateMode == DuplicateMode.skip && await File(target).exists()) {
      f
        ..status = TransferStatus.skipped
        ..transferred = f.size
        ..savedPath = target;
      return true;
    }
    final key = sha256.convert(utf8.encode('dl|$peerId|${rf.query}|${rf.size}')).toString().substring(0, 32);
    final part = File(p.join(destDir, partialDirName, '$key.part'));
    await part.parent.create(recursive: true);
    StreamingHasher? hasher;
    RandomAccessFile? raf;
    try {
      raf = await part.open(mode: FileMode.append);
      hasher = await StreamingHasher.create(rf.size);
      var offset = await raf.length();
      if (offset > rf.size) {
        await raf.truncate(0);
        offset = 0;
      }
      if (offset > 0) {
        await raf.setPosition(0);
        var done = 0;
        while (done < offset) {
          final b = await raf.read(offset - done > 4 << 20 ? 4 << 20 : offset - done);
          if (b.isEmpty) break;
          await hasher.add(b);
          done += b.length;
        }
        await raf.setPosition(offset);
      }
      f.transferred = offset;
      while (offset < rf.size) {
        while (_paused && !_cancelled) {
          await Future.delayed(const Duration(milliseconds: 200));
        }
        if (_cancelled) return false;
        final len = rf.size - offset < chunkSize ? rf.size - offset : chunkSize;
        final o = offset;
        final (status, data) = await _net(
            () => _client!.getBytes('/fs/read', {...rf.query, 'offset': '$o', 'len': '$len'}, onRequest: (r) => _req = r), f);
        if (status != 200) {
          final msg = _errorText(data);
          throw TransferysException(ErrorCode.fileUnreadable, msg ?? 'Lecture refusée par ${job.peerName} ($status).');
        }
        if (data.isEmpty) throw TransferysException(ErrorCode.fileUnreadable, 'Le fichier a changé sur ${job.peerName}.');
        try {
          await Future.wait([raf.writeFrom(data), hasher.add(data)]);
        } catch (e) {
          if (isDiskFull(e)) throw TransferysException(ErrorCode.diskFull, 'Espace disque insuffisant dans $destDir.');
          rethrow;
        }
        offset += data.length;
        f.transferred = offset;
        job.speed.add(job.transferredBytes);
        job.notify();
      }
      await raf.flush();
      await raf.close();
      raf = null;
      final mine = await hasher.close();
      hasher = null;
      final (hs, hb) = await _net(() async {
        final r = await _client!.json('GET', '/fs/hash', query: rf.query, timeout: const Duration(minutes: 5));
        return (r.status, r.body);
      }, f);
      if (hs != 200 || hb['sha256'] != mine) {
        await part.delete();
        f.status = TransferStatus.failed;
        f.error = hs != 200 ? 'Vérification impossible.' : 'Fichier corrompu (SHA-256 différent) : réessayez.';
        return false;
      }
      var dest = target;
      if (await File(dest).exists()) {
        if (duplicateMode == DuplicateMode.replace) {
          try {
            await File(dest).delete();
          } catch (_) {
            dest = uniquePath(dest);
          }
        } else {
          dest = uniquePath(dest);
        }
      }
      final saved = await moveFile(part, dest);
      if (rf.modified != null) {
        try {
          await saved.setLastModified(rf.modified!);
        } catch (_) {}
      }
      f
        ..savedPath = saved.path
        ..transferred = f.size
        ..status = TransferStatus.done;
      job.notify(force: true);
      await onFileSaved?.call(saved.path).catchError((_) {});
      return true;
    } catch (e) {
      if (_cancelled) return false;
      f.status = TransferStatus.failed;
      f.error = e is TransferysException ? e.message : 'Erreur : $e';
      if (e is TransferysException && (e.code == ErrorCode.diskFull || e.code == ErrorCode.unreachable)) rethrow;
      return false;
    } finally {
      hasher?.dispose();
      try {
        await raf?.close();
      } catch (_) {}
    }
  }

  String? _errorText(List<int> body) {
    try {
      final j = jsonDecode(utf8.decode(body));
      if (j is Map) return j['message'] as String? ?? j['error'] as String?;
    } catch (_) {}
    return null;
  }
}
