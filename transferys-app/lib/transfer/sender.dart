// Envoi de fichiers vers un appareil de confiance : morceaux de 8 Mo,
// reprise automatique après coupure (jusqu'à 10 minutes), SHA-256 vérifié
// par le destinataire, pause / reprise / annulation.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';


import '../core/errors.dart';
import '../core/format.dart';
import '../core/models.dart';
import 'client.dart';
import 'file_source.dart';
import 'hasher.dart';
import 'job.dart';
import 'protocol.dart';


/// Erreur qui arrête tout le transfert (pas seulement le fichier en cours).
class _Fatal implements Exception {
  _Fatal(this.status, this.message);
  final TransferStatus status;
  final String message;
}

class _SessionLost implements Exception {}

class SendJob {
  SendJob({
    required this.job,
    required this.sources,
    required this.createClient,
    required this.resolveAddress,
    this.reconnectWindow = const Duration(minutes: 10),
    this.onActivity,
    this.sessionExtra,
  });

  /// Champs ajoutés à la demande d'envoi (dossier cible, jeton de demande).
  final Map<String, Object?>? sessionExtra;

  final TransferJob job;
  final List<FileSource> sources;

  /// Crée un client vers l'adresse courante de l'appareil.
  final PeerClient Function(String host) createClient;

  /// Adresse actuelle de l'appareil (peut changer si le Wi-Fi se reconnecte).
  final Future<String?> Function() resolveAddress;
  final Duration reconnectWindow;
  final void Function()? onActivity;

  PeerClient? _client;
  String? _host;
  bool _paused = false;
  bool _cancelled = false;
  HttpClientRequest? _currentReq;
  final _offsets = <String, int>{};
  final _actions = <String, String>{};

  String get _sid => job.id;

  Future<void> run() async {
    job.onPause = pause;
    job.onResume = resume;
    job.onCancel = cancel;
    try {
      _host = await resolveAddress();
      if (_host == null) {
        throw TransferysException(ErrorCode.unreachable, '${job.peerName} est introuvable sur le réseau.');
      }
      _client = createClient(_host!);
      job.status = TransferStatus.waiting;
      job.notify(force: true);
      await _withReconnect(_openSession, fileLabel: null);
      if (_cancelled) return;
      job.status = TransferStatus.running;
      job.notify(force: true);

      for (var i = 0; i < sources.length; i++) {
        if (_cancelled) break;
        final f = job.files[i];
        if (_actions[f.fileId] == 'skip') {
          f.status = TransferStatus.skipped;
          f.transferred = f.size;
          job.notify(force: true);
          continue;
        }
        await _sendFile(i);
      }
      if (_cancelled) return;
      try {
        await _client!.json('POST', '/session/$_sid/done');
      } catch (_) {}
      job.status = job.failedCount > 0 ? TransferStatus.failed : TransferStatus.done;
      if (job.status == TransferStatus.failed) {
        final first = job.files.where((x) => x.error != null).map((x) => x.error).firstOrNull;
        job.error ??= '${job.failedCount} fichier(s) n\'ont pas pu être envoyés.${first != null ? ' Raison : $first' : ''}';
      }
    } on _Fatal catch (f) {
      job.status = f.status;
      job.error = f.message;
      for (final tf in job.files) {
        if (!tf.status.isFinal) tf.status = f.status == TransferStatus.cancelled ? TransferStatus.cancelled : TransferStatus.failed;
      }
    } on TransferysException catch (e) {
      job.status = TransferStatus.failed;
      job.error = e.message;
      for (final tf in job.files) {
        if (!tf.status.isFinal) tf.status = TransferStatus.failed;
      }
    } catch (e) {
      job.status = TransferStatus.failed;
      job.error = describeNetworkError(e, peerName: job.peerName).message;
      for (final tf in job.files) {
        if (!tf.status.isFinal) tf.status = TransferStatus.failed;
      }
    } finally {
      if (_cancelled) {
        job.status = TransferStatus.cancelled;
        job.error ??= 'Transfert annulé.';
        for (final tf in job.files) {
          if (!tf.status.isFinal) tf.status = TransferStatus.cancelled;
        }
      }
      job.notify(force: true);
      _client?.close();
    }
  }

  // ------------------------------------------------------------- commandes
  void pause() {
    if (_paused || !job.isActive) return;
    _paused = true;
    job.status = TransferStatus.paused;
    job.notify(force: true);
    _client?.json('POST', '/session/$_sid/pause').catchError((_) => ApiResponse(0, {}));
  }

  void resume() {
    if (!_paused) return;
    _paused = false;
    job.status = TransferStatus.running;
    job.speed.reset();
    job.notify(force: true);
    _client?.json('POST', '/session/$_sid/resume').catchError((_) => ApiResponse(0, {}));
  }

  void cancel() {
    if (_cancelled || !job.isActive) return;
    _cancelled = true;
    _paused = false;
    try {
      _currentReq?.abort();
    } catch (_) {}
    final c = _client;
    if (c != null) {
      // Prévenir le destinataire (au mieux) pour qu'il supprime les morceaux.
      final h = createClient(_host!);
      h.json('POST', '/session/$_sid/cancel', timeout: const Duration(seconds: 5)).catchError((_) => ApiResponse(0, {})).whenComplete(h.close);
    }
    job.status = TransferStatus.cancelled;
    job.notify(force: true);
  }

  // --------------------------------------------------------------- session
  Future<void> _openSession() async {
    final body = {
      ...?sessionExtra,
      'sessionId': _sid,
      'files': [
        for (var i = 0; i < sources.length; i++)
          {
            'fileId': job.files[i].fileId,
            'relPath': sources[i].relPath,
            'size': sources[i].size,
            'modified': sources[i].modified.millisecondsSinceEpoch,
          }
      ],
    };
    // Long délai : le destinataire doit peut-être accepter (2 min max).
    final r = await _client!.json('POST', '/session', body: body, timeout: const Duration(minutes: 3));
    if (r.status >= 500 && r.error == 'internal') throw const HttpException('Erreur temporaire du destinataire');
    if (r.ok && r.body['accepted'] == true) {
      for (final a in (r.body['files'] as List)) {
        final m = (a as Map).cast<String, dynamic>();
        final id = m['fileId'].toString();
        _actions[id] = m['action'] as String? ?? 'receive';
        _offsets[id] = (m['offset'] as num?)?.toInt() ?? 0;
      }
      for (final f in job.files) {
        if (f.status != TransferStatus.done) f.transferred = _offsets[f.fileId] ?? 0;
      }
      return;
    }
    _raiseFor(r);
  }

  Never _raiseFor(ApiResponse r) {
    switch (r.error) {
      case 'rejected':
        throw _Fatal(TransferStatus.rejected, '${job.peerName} a refusé le transfert.');
      case 'disk_full':
        final need = (r.body['needed'] as num?)?.toInt();
        final free = (r.body['free'] as num?)?.toInt();
        throw _Fatal(
            TransferStatus.failed,
            need != null && free != null
                ? 'Espace disque insuffisant sur ${job.peerName} : il faut ${formatSize(need)}, il reste ${formatSize(free)}.'
                : 'Espace disque insuffisant sur ${job.peerName}.');
      case 'not_paired':
        throw _Fatal(TransferStatus.failed,
            '${job.peerName} ne vous reconnaît plus comme appareil de confiance. Retirez-le de vos appareils de confiance puis appairez-le à nouveau.');
      case 'cancelled':
        throw _Fatal(TransferStatus.cancelled, 'Transfert annulé par ${job.peerName}.');
      case 'unknown_session':
        throw _SessionLost();
      case 'read_only':
        throw _Fatal(TransferStatus.failed, 'Ce dossier de ${job.peerName} est en lecture seule.');
      case 'write_failed':
        throw _Fatal(TransferStatus.failed,
            'Impossible d\'écrire sur ${job.peerName} : ${r.body['message'] ?? 'dossier de réception inaccessible'}.');
      default:
        throw _Fatal(TransferStatus.failed, 'Erreur sur ${job.peerName} (${r.status} ${r.error ?? ''}).');
    }
  }

  /// Exécute [action] ; si le réseau coupe, attend et réessaie (avec
  /// recherche de la nouvelle adresse IP) pendant [reconnectWindow].
  Future<T> _withReconnect<T>(Future<T> Function() action, {required TransferFile? fileLabel}) async {
    DateTime? lostAt;
    var attempt = 0;
    while (true) {
      if (_cancelled) throw _Fatal(TransferStatus.cancelled, 'Transfert annulé.');
      try {
        final r = await action();
        if (lostAt != null) {
          job.status = _paused ? TransferStatus.paused : TransferStatus.running;
          if (fileLabel != null) fileLabel.status = TransferStatus.running;
          job.notify(force: true);
        }
        return r;
      } on _SessionLost {
        // Le destinataire a redémarré : on recrée la session (les morceaux
        // déjà reçus sont retrouvés sur son disque).
        await _openSession();
        lostAt = null;
        continue;
      } catch (e) {
        if (_cancelled) throw _Fatal(TransferStatus.cancelled, 'Transfert annulé.');
        if (e is TransferysException && e.code == ErrorCode.certificateChanged) rethrow;
        if (!isNetworkError(e)) rethrow;
        lostAt ??= DateTime.now();
        if (DateTime.now().difference(lostAt) > reconnectWindow) {
          final d = describeNetworkError(e, peerName: job.peerName);
          throw _Fatal(TransferStatus.failed, 'Connexion perdue avec ${job.peerName} depuis plus de 10 minutes. ${d.message}');
        }
        job.status = TransferStatus.reconnecting;
        job.error = 'Connexion perdue, nouvelle tentative…';
        if (fileLabel != null) fileLabel.status = TransferStatus.reconnecting;
        job.speed.reset();
        job.notify(force: true);
        const delays = [1, 2, 3, 5, 8, 10];
        await Future.delayed(Duration(seconds: delays[attempt < delays.length ? attempt : delays.length - 1]));
        attempt++;
        final newHost = await resolveAddress();
        if (newHost != null && newHost != _host) {
          _host = newHost;
        }
        _client?.close();
        _client = createClient(_host!);
        job.error = null;
      }
    }
  }

  // -------------------------------------------------------------- fichiers
  Future<void> _sendFile(int index) async {
    final src = sources[index];
    final f = job.files[index];
    f.status = TransferStatus.running;
    job.notify(force: true);
    SourceReader? raf;
    StreamingHasher? hasher;
    try {
      try {
        raf = await src.open();
      } catch (e) {
        f.status = TransferStatus.failed;
        f.error = 'Fichier illisible sur cet appareil : ${e is FileSystemException ? e.message : e}';
        await _reportFailure(f);
        return;
      }
      final file = raf;
      hasher = await StreamingHasher.create(src.size);
      var confirmed = 0; // octets confirmés par le destinataire ET hachés
      var serverOffset = _offsets[f.fileId] ?? 0;
      var integrityRetries = 0;
      String? digest;

      Future<void> rehashTo(int target) async {
        hasher?.dispose();
        hasher = await StreamingHasher.create(src.size);
        digest = null;
        await file.setPosition(0);
        var done = 0;
        while (done < target) {
          final n = target - done > 4 << 20 ? 4 << 20 : target - done;
          final b = await file.read(n);
          if (b.isEmpty) break;
          await hasher!.add(b);
          done += b.length;
        }
        confirmed = done;
      }

      while (true) {
        if (_cancelled) return;
        if (serverOffset > src.size) serverOffset = 0;
        if (serverOffset != confirmed) await rehashTo(serverOffset);

        if (confirmed >= src.size) {
          // Fichier entièrement transmis : vérification SHA-256 par le destinataire.
          if (digest == null) {
            digest = await hasher!.close();
          }
          final r = await _withReconnect(() async {
            final r = await _client!.json('POST', '/session/$_sid/file/${f.fileId}/finish', body: {'sha256': digest});
            if (r.error == 'unknown_session') throw _SessionLost();
            if (r.status >= 500 && r.error == 'internal') throw const HttpException('Erreur temporaire du destinataire');
            return r;
          }, fileLabel: f);
          if (r.ok) {
            f.transferred = f.size;
            f.status = TransferStatus.done;
            job.notify(force: true);
            return;
          }
          if (r.error == 'integrity') {
            integrityRetries++;
            if (integrityRetries > 1) {
              f.status = TransferStatus.failed;
              f.error = 'Fichier corrompu pendant le transfert (SHA-256 différent).';
              await _reportFailure(f);
              return;
            }
            serverOffset = 0;
            confirmed = -1; // force un nouveau hachage depuis 0
            f.transferred = 0;
            continue;
          }
          if (r.error == 'incomplete') {
            serverOffset = (r.body['offset'] as num).toInt();
            confirmed = -1;
            continue;
          }
          _raiseFor(r);
        }

        // Pause : on attend entre deux morceaux.
        while (_paused && !_cancelled) {
          await Future.delayed(const Duration(milliseconds: 200));
        }
        if (_cancelled) return;

        final len = src.size - confirmed < chunkSize ? src.size - confirmed : chunkSize;
        await file.setPosition(confirmed);
        final data = await file.read(len);
        if (data.length != len) {
          f.status = TransferStatus.failed;
          f.error = 'Le fichier a été modifié ou déplacé pendant l\'envoi (${data.length} octets lus au lieu de $len).';
          await _reportFailure(f);
          return;
        }
        final base = confirmed;
        final r = await _withReconnect(() async {
          final r = await _client!.putChunk(_sid, f.fileId, base, data,
              onRequest: (req) => _currentReq = req,
              onSent: (n) {
                f.transferred = base + n;
                job.speed.add(job.transferredBytes);
                job.notify();
              });
          if (r.error == 'unknown_session') throw _SessionLost();
          // Erreur interne passagère (appli fermée en plein morceau…) : on réessaie.
          if (r.status >= 500 && r.error == 'internal') throw const HttpException('Erreur temporaire du destinataire');
          return r;
        }, fileLabel: f);
        _currentReq = null;
        onActivity?.call();
        if (r.ok) {
          final newOff = (r.body['offset'] as num?)?.toInt() ?? base + len;
          if (r.body['done'] == true) {
            f.transferred = f.size;
            f.status = TransferStatus.done;
            job.notify(force: true);
            return;
          }
          await _absorb(hasher!, data, base, newOff);
          confirmed = newOff;
          serverOffset = newOff;
          f.transferred = newOff;
          if (job.remotePaused) {
            job.remotePaused = false;
            job.status = _paused ? TransferStatus.paused : TransferStatus.running;
          }
          continue;
        }
        switch (r.status) {
          case 409:
            final so = (r.body['offset'] as num).toInt();
            if (so >= base && so <= base + len) {
              await _absorb(hasher!, data, base, so);
              confirmed = so;
            }
            serverOffset = so;
            f.transferred = so;
            continue;
          case 423:
            // Mis en pause par le destinataire.
            job.remotePaused = true;
            job.status = TransferStatus.paused;
            f.transferred = confirmed;
            job.notify(force: true);
            await Future.delayed(const Duration(seconds: 2));
            continue;
          default:
            _raiseFor(r);
        }
      }
    } on _Fatal {
      rethrow;
    } catch (e) {
      if (_cancelled) return;
      f.status = TransferStatus.failed;
      f.error = e is TransferysException ? e.message : 'Erreur : $e';
      await _reportFailure(f);
    } finally {
      hasher?.dispose();
      try {
        await raf?.close();
      } catch (_) {}
      await src.release();
    }
  }

  /// Informe le destinataire de la raison d'un échec (affichée chez lui).
  Future<void> _reportFailure(TransferFile f) async {
    try {
      await _client?.json('POST', '/session/$_sid/file/${f.fileId}/fail',
          body: {'message': f.error}, timeout: const Duration(seconds: 5));
    } catch (_) {}
  }

  /// Ajoute au hachage la partie [base, upTo) du morceau en mémoire.
  Future<void> _absorb(StreamingHasher h, Uint8List data, int base, int upTo) async {
    if (upTo <= base) return;
    await h.add(Uint8List.sublistView(data, 0, upTo - base));
  }
}
