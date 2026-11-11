// Serveur HTTPS local : identité, appairage, réception des fichiers.
import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as p;

import '../core/errors.dart';
import '../core/models.dart';
import '../core/settings.dart';
import '../core/stores.dart';
import '../network/net_utils.dart';
import '../security/identity.dart';
import '../security/pairing.dart';
import 'job.dart';
import 'protocol.dart';
import 'fs_service.dart';
import 'receiver.dart';
import 'tunnel.dart';

/// Code d'appairage à afficher sur cet appareil.
class PairingPrompt {
  PairingPrompt({required this.pairId, required this.peerName, required this.platform, required this.code});
  final String pairId;
  final String peerName;
  final DevicePlatform platform;
  final String code;
}

/// Ce que le serveur attend du reste de l'appli (moteur / interface).
abstract class ServerDelegate {
  DeviceIdentity get identity;
  Settings get settings;
  TrustStore get trust;
  Map<String, dynamic> infoJson();

  /// Demande à l'utilisateur d'accepter ou refuser une réception.
  Future<bool> confirmIncoming(IncomingRequest r);
  void showPairingCode(PairingPrompt prompt);
  void closePairingCode(String pairId, {required bool success, String? message});
  Future<int?> freeSpace(String dir);
  void onReceiveStarted(TransferJob job);
  Future<void> onReceiveEnded(TransferJob job);
  Future<void> onFileSaved(String path);

  // Accès à distance
  FsService get fs;
  TunnelHub get tunnels;
  Map<String, Offer> get offers;
  Future<Map<String, Object?>> remoteInfo();

  /// Jeton donné à un appareil à qui on a demandé de nous envoyer des
  /// fichiers : la réception est alors acceptée sans confirmation.
  bool consumePushToken(String deviceId, String token);
}

/// Adresse distante normalisée (« ::ffff:192.168.1.5 » → « 192.168.1.5 »).
String remoteAddressOf(HttpRequest req) {
  final a = req.connectionInfo?.remoteAddress.address ?? '';
  return a.startsWith('::ffff:') ? a.substring(7) : a;
}

bool isLocalAddress(String a) {
  if (a == '127.0.0.1' || a == '::1') return true;
  if (isPrivateIPv4(a)) return true;
  final l = a.toLowerCase();
  return l.startsWith('fe8') || l.startsWith('fc') || l.startsWith('fd');
}

class _PairingState {
  _PairingState({
    required this.pairId,
    required this.peerId,
    required this.name,
    required this.platform,
    required this.fingerprint,
    required this.port,
    required this.nonceB,
  });
  final String pairId;
  final String peerId;
  final String name;
  final DevicePlatform platform;
  final String fingerprint;
  final int port;
  final String nonceB;
  final DateTime created = DateTime.now();
  String? code;
  int attempts = 0;
}

class TransferServer {
  TransferServer(this.delegate);
  final ServerDelegate delegate;
  HttpServer? _server;
  int? boundPort;
  String? lastError;
  _PairingState? _pairing;
  final sessions = <String, ReceiveSession>{};
  Timer? _janitor;

  static const pairingTimeout = Duration(minutes: 3);
  static const decisionTimeout = Duration(minutes: 2);

  Future<void> start(int preferredPort) async {
    if (_server != null) return;
    final ctx = delegate.identity.serverContext();
    // IPv4 + IPv6 sur le même port (l'IPv6 sert à l'accès à distance).
    Future<HttpServer> bind(int port) async {
      try {
        return await HttpServer.bindSecure(InternetAddress.anyIPv6, port, ctx, v6Only: false);
      } on SocketException catch (e) {
        if (e.osError?.errorCode == 98 || e.osError?.errorCode == 10048 || e.message.contains('in use')) rethrow;
        return HttpServer.bindSecure(InternetAddress.anyIPv4, port, ctx);
      }
    }

    try {
      _server = await bind(preferredPort);
    } on SocketException {
      // Port déjà pris (autre logiciel) : port libre au hasard, annoncé par la découverte.
      _server = await bind(0);
    }
    _server!.idleTimeout = const Duration(seconds: 60);
    _server!.autoCompress = false;
    boundPort = _server!.port;
    _stopping = false;
    _server!.listen(_handle, onError: (_) {});
    _janitor = Timer.periodic(const Duration(minutes: 5), (_) => _cleanup());
  }

  bool _stopping = false;

  Future<void> stop() async {
    _stopping = true;
    _janitor?.cancel();
    for (final s in sessions.values) {
      await s.closeAll();
    }
    await _server?.close(force: true);
    _server = null;
  }

  void _cleanup() {
    final now = DateTime.now();
    sessions.removeWhere((_, s) {
      final stale = now.difference(s.lastActivity) > const Duration(hours: 12);
      if (stale) s.closeAll();
      return stale;
    });
  }

  // ---------------------------------------------------------------- routage
  Future<void> _handle(HttpRequest req) async {
    try {
      final seg = req.uri.pathSegments;
      if (seg.length < 3 || seg[0] != 'api' || seg[1] != 'v1') {
        return await sendJson(req, 404, {'error': 'not_found'});
      }
      final route = seg.sublist(2);
      final m = req.method;
      if (m == 'GET' && route.length == 1 && route[0] == 'info') return await _info(req);
      if (m == 'POST' && route.length == 2 && route[0] == 'pair') {
        switch (route[1]) {
          case 'hello':
            return await _pairHello(req);
          case 'nonce':
            return await _pairNonce(req);
          case 'confirm':
            return await _pairConfirm(req);
          case 'cancel':
            return await _pairCancel(req);
        }
      }
      // Tout le reste exige un appareil de confiance.
      final dev = _authenticate(req);
      if (dev == null) {
        await req.drain<void>().catchError((_) {});
        return await sendJson(req, 401, {'error': 'not_paired'});
      }
      if (m == 'POST' && route.length == 1 && route[0] == 'session') return await _createSession(req, dev);
      if (m == 'GET' && route.length == 1 && route[0] == 'remote') return await sendJson(req, 200, await delegate.remoteInfo());
      if (route.isNotEmpty && route[0] == 'tunnel') return await _tunnel(req, dev, route);
      if (route.isNotEmpty && route[0] == 'fs') return await _fs(req, dev, route);
      if (route.length >= 2 && route[0] == 'session') {
        final s = sessions[route[1]];
        if (s == null || s.from.id != dev.id) {
          await req.drain<void>().catchError((_) {});
          return await sendJson(req, 404, {'error': 'unknown_session'});
        }
        s.lastActivity = DateTime.now();
        if (route.length == 4 && route[2] == 'file') {
          final rf = s.files[route[3]];
          if (rf == null) return await sendJson(req, 404, {'error': 'unknown_file'});
          if (m == 'PUT') return await _putChunk(req, s, rf);
          if (m == 'GET') return await sendJson(req, 200, {'offset': rf.offset, 'done': rf.done, 'paused': s.pausedByReceiver});
        }
        if (m == 'POST' && route.length == 5 && route[2] == 'file' && route[4] == 'fail') {
          final rf = s.files[route[3]];
          final j = await readJsonBody(req);
          if (rf != null && !rf.done) {
            await rf.discardPart();
            rf.view
              ..status = TransferStatus.failed
              ..error = (j['message'] as String?) ?? 'Échec sur l\'appareil d\'origine.';
            s.job.notify(force: true);
          }
          return await sendJson(req, 200, {'ok': true});
        }
        if (m == 'POST' && route.length == 5 && route[2] == 'file' && route[4] == 'finish') {
          final rf = s.files[route[3]];
          if (rf == null) return await sendJson(req, 404, {'error': 'unknown_file'});
          return await _finishFile(req, s, rf);
        }
        if (m == 'POST' && route.length == 3) {
          switch (route[2]) {
            case 'pause':
              s.job.remotePaused = true;
              s.job.status = TransferStatus.paused;
              s.job.notify(force: true);
              return await sendJson(req, 200, {'ok': true});
            case 'resume':
              s.job.remotePaused = false;
              if (!s.pausedByReceiver) s.job.status = TransferStatus.running;
              s.job.notify(force: true);
              return await sendJson(req, 200, {'ok': true});
            case 'cancel':
              await _endSession(s, TransferStatus.cancelled, error: 'Annulé par ${s.from.name}.');
              return await sendJson(req, 200, {'ok': true});
            case 'done':
              await _endSession(s, null);
              return await sendJson(req, 200, {'ok': true});
          }
        }
      }
      await req.drain<void>().catchError((_) {});
      return await sendJson(req, 404, {'error': 'not_found'});
    } catch (e) {
      // Appli en cours de fermeture : on coupe sans répondre, l'autre
      // appareil reprendra quand on sera de retour.
      if (_stopping) {
        try {
          (await req.response.detachSocket(writeHeaders: false)).destroy();
        } catch (_) {}
        return;
      }
      try {
        await sendJson(req, 500, {'error': 'internal', 'message': '$e'});
      } catch (_) {}
    }
  }

  TrustedDevice? _authenticate(HttpRequest req) {
    final id = req.headers.value(headerDeviceId);
    final auth = req.headers.value(headerAuth);
    if (id == null || auth == null || !auth.startsWith('Bearer ')) return null;
    final dev = delegate.trust.get(id);
    if (dev == null) return null;
    if (!constantTimeEquals(auth.substring(7), dev.secret)) return null;
    final addr = remoteAddressOf(req);
    if (addr.isNotEmpty && isLocalAddress(addr)) dev.lastAddress = addr;
    return dev;
  }

  Future<void> _info(HttpRequest req) {
    final info = Map<String, dynamic>.from(delegate.infoJson());
    // Indique à l'appelant s'il est toujours dans nos appareils de confiance.
    info['paired'] = _authenticate(req) != null;
    return sendJson(req, 200, info);
  }

  // -------------------------------------------------------------- appairage
  Future<void> _pairHello(HttpRequest req) async {
    final j = await readJsonBody(req);
    // L'appairage ne se fait que sur le réseau local, jamais depuis Internet.
    if (!isLocalAddress(remoteAddressOf(req))) {
      return sendJson(req, 403, {'error': 'pairing_remote'});
    }
    final cur = _pairing;
    if (cur != null && DateTime.now().difference(cur.created) < pairingTimeout && cur.peerId != j['id']) {
      return sendJson(req, 409, {'error': 'busy'});
    }
    if (cur != null) delegate.closePairingCode(cur.pairId, success: false);
    final st = _PairingState(
      pairId: randomToken(12),
      peerId: j['id'] as String,
      name: (j['name'] as String?) ?? 'Appareil',
      platform: platformFromString(j['platform'] as String?),
      fingerprint: j['fingerprint'] as String,
      port: (j['port'] as num?)?.toInt() ?? Settings.defaultPort,
      nonceB: randomToken(16),
    );
    _pairing = st;
    return sendJson(req, 200, {
      'pairId': st.pairId,
      'commit': commitment(st.nonceB),
      ...delegate.infoJson(),
    });
  }

  Future<void> _pairNonce(HttpRequest req) async {
    final j = await readJsonBody(req);
    final st = _pairing;
    if (st == null || st.pairId != j['pairId'] || st.code != null) return sendJson(req, 404, {'error': 'no_pairing'});
    final nonceA = j['nonceA'] as String;
    st.code = pairingCode(
      fingerprintA: st.fingerprint,
      fingerprintB: delegate.identity.fingerprint,
      nonceA: nonceA,
      nonceB: st.nonceB,
    );
    delegate.showPairingCode(PairingPrompt(pairId: st.pairId, peerName: st.name, platform: st.platform, code: st.code!));
    return sendJson(req, 200, {'nonceB': st.nonceB});
  }

  Future<void> _pairConfirm(HttpRequest req) async {
    final j = await readJsonBody(req);
    final st = _pairing;
    if (st == null || st.pairId != j['pairId'] || st.code == null) return sendJson(req, 404, {'error': 'no_pairing'});
    if (DateTime.now().difference(st.created) > pairingTimeout) {
      _pairing = null;
      delegate.closePairingCode(st.pairId, success: false, message: 'Délai d\'appairage dépassé.');
      return sendJson(req, 410, {'error': 'expired'});
    }
    if (!constantTimeEquals((j['code'] as String?) ?? '', st.code!)) {
      st.attempts++;
      if (st.attempts >= 3) {
        _pairing = null;
        delegate.closePairingCode(st.pairId, success: false, message: 'Trop de codes erronés : appairage annulé.');
        return sendJson(req, 403, {'error': 'too_many_attempts'});
      }
      return sendJson(req, 401, {'error': 'wrong_code', 'remaining': 3 - st.attempts});
    }
    final secret = j['secret'] as String?;
    if (secret == null || secret.length < 32) return sendJson(req, 400, {'error': 'bad_secret'});
    await delegate.trust.put(TrustedDevice(
      id: st.peerId,
      name: st.name,
      platform: st.platform,
      fingerprint: st.fingerprint,
      secret: secret,
      pairedAt: DateTime.now(),
      lastAddress: remoteAddressOf(req),
      lastPort: st.port,
    ));
    _pairing = null;
    delegate.closePairingCode(st.pairId, success: true, message: '${st.name} est maintenant un appareil de confiance.');
    return sendJson(req, 200, {'ok': true});
  }

  Future<void> _pairCancel(HttpRequest req) async {
    final j = await readJsonBody(req);
    final st = _pairing;
    if (st != null && st.pairId == j['pairId']) {
      _pairing = null;
      delegate.closePairingCode(st.pairId, success: false, message: 'Appairage annulé par ${st.name}.');
    }
    return sendJson(req, 200, {'ok': true});
  }

  /// Annule l'appairage affiché localement (bouton « Annuler »).
  void cancelLocalPairing() {
    final st = _pairing;
    _pairing = null;
    if (st != null) delegate.closePairingCode(st.pairId, success: false);
  }

  // -------------------------------------------------------------- réception
  Future<void> _createSession(HttpRequest req, TrustedDevice dev) async {
    final j = await readJsonBody(req);
    final sid = j['sessionId'] as String?;
    final list = (j['files'] as List?) ?? const [];
    if (sid == null || sid.length < 8 || list.isEmpty) return sendJson(req, 400, {'error': 'bad_request'});

    // Requête renvoyée après une coupure : même réponse.
    final existing = sessions[sid];
    if (existing != null) {
      if (existing.acceptResponse != null) return sendJson(req, 200, existing.acceptResponse!);
      if (existing.pendingDecision != null) {
        final r = await existing.pendingDecision!;
        return sendJson(req, r['accepted'] == true ? 200 : (r['status'] as int? ?? 403), r);
      }
    }

    final infos = list.map((e) => IncomingFileInfo.fromJson((e as Map).cast<String, dynamic>())).toList();
    final settings = delegate.settings;
    var receiveDir = settings.receiveDir;
    var autoAccept = false;
    // Dépôt dans un dossier partagé ouvert en écriture (explorateur distant).
    final target = j['target'];
    if (target is Map) {
      try {
        final shareId = target['share'] as String;
        if (!delegate.fs.writable(shareId)) {
          return await sendJson(req, 403, {'error': 'read_only', 'message': 'Ce dossier est en lecture seule.'});
        }
        receiveDir = delegate.fs.resolve(shareId, (target['path'] as String?) ?? '');
        autoAccept = true;
      } on FsException catch (e) {
        return await sendJson(req, 404, {'error': e.code, 'message': e.message});
      }
    }
    final token = j['token'] as String?;
    if (token != null && delegate.consumePushToken(dev.id, token)) autoAccept = true;
    final job = TransferJob(
      id: sid,
      direction: TransferDirection.receive,
      peerName: dev.name,
      peerId: dev.id,
      files: [for (final f in infos) TransferFile(fileId: f.fileId, relPath: f.relPath, size: f.size)],
      folder: receiveDir,
    );
    final s = ReceiveSession(id: sid, from: dev, job: job, receiveDir: receiveDir);
    for (var i = 0; i < infos.length; i++) {
      s.files[infos[i].fileId] = ReceiveFile(infos[i], job.files[i]);
    }
    sessions[sid] = s;

    final decision = _decide(s, settings, autoAccept: autoAccept);
    s.pendingDecision = decision;
    final r = await decision;
    s.pendingDecision = null;
    if (r['accepted'] == true) {
      s.acceptResponse = r;
      return sendJson(req, 200, r);
    }
    sessions.remove(sid);
    return sendJson(req, r['status'] as int? ?? 403, r);
  }

  Future<Map<String, dynamic>> _decide(ReceiveSession s, Settings settings, {bool autoAccept = false}) async {
    try {
      await Directory(s.receiveDir).create(recursive: true);
    } catch (e) {
      return {'accepted': false, 'status': 500, 'error': 'write_failed', 'message': 'Dossier de réception inaccessible : ${s.receiveDir}'};
    }
    await s.prepare(settings.duplicateMode);

    // Espace disque suffisant ?
    final need = s.bytesNeeded;
    final free = await delegate.freeSpace(s.receiveDir);
    if (free != null && free < need + diskMargin) {
      return {'accepted': false, 'status': 507, 'error': 'disk_full', 'needed': need, 'free': free};
    }

    if (settings.confirmBeforeReceive && !autoAccept) {
      final req = IncomingRequest(sessionId: s.id, from: s.from, files: s.files.values.map((f) => f.info).toList());
      bool ok;
      try {
        ok = await delegate.confirmIncoming(req).timeout(decisionTimeout, onTimeout: () => false);
      } catch (_) {
        ok = false;
      }
      if (!ok) return {'accepted': false, 'status': 403, 'error': 'rejected'};
    }

    s.accepted = true;
    s.job.status = TransferStatus.running;
    s.job.onPause = () {
      s.pausedByReceiver = true;
      s.job.status = TransferStatus.paused;
      s.job.notify(force: true);
    };
    s.job.onResume = () {
      s.pausedByReceiver = false;
      s.job.status = TransferStatus.running;
      s.job.notify(force: true);
    };
    s.job.onCancel = () => _endSession(s, TransferStatus.cancelled, error: 'Réception annulée.');
    delegate.onReceiveStarted(s.job);
    return {
      'accepted': true,
      'files': [
        for (final rf in s.files.values) {'fileId': rf.info.fileId, 'action': rf.skip ? 'skip' : 'receive', 'offset': rf.offset},
      ],
    };
  }

  Future<void> _putChunk(HttpRequest req, ReceiveSession s, ReceiveFile rf) async {
    if (s.failure != null) {
      await req.drain<void>().catchError((_) {});
      return sendJson(req, s.failure!.$1, s.failure!.$2);
    }
    if (s.cancelled) {
      await req.drain<void>().catchError((_) {});
      return sendJson(req, 410, {'error': 'cancelled'});
    }
    if (s.pausedByReceiver) {
      await req.drain<void>().catchError((_) {});
      return sendJson(req, 423, {'error': 'paused'});
    }
    if (rf.skip || rf.done) {
      await req.drain<void>().catchError((_) {});
      return sendJson(req, 200, {'offset': rf.info.size, 'done': true});
    }
    final offset = int.tryParse(req.uri.queryParameters['offset'] ?? '');
    final result = await rf.locked<(int, Map<String, Object?>)>(() async {
      try {
        await rf.ensureOpen();
      } catch (e) {
        return writeErrorResponse(e);
      }
      if (offset != rf.offset) return (409, {'error': 'offset_mismatch', 'offset': rf.offset});
      rf.view.status = TransferStatus.running;
      final buf = BytesBuilder(copy: false);
      Object? writeError;
      Future<void> flush() async {
        if (buf.isEmpty || writeError != null) return;
        final data = buf.takeBytes();
        if (rf.offset + data.length > rf.info.size) {
          writeError = const FormatException('trop de données');
          return;
        }
        try {
          await rf.write(data);
        } catch (e) {
          writeError = e;
        }
        rf.view.transferred = rf.offset;
        s.job.speed.add(s.job.transferredBytes);
        s.job.notify();
      }

      try {
        // Délai de garde : si le Wi-Fi disparaît, la connexion TCP peut rester
        // « ouverte » sans plus rien transmettre.
        await for (final d in req.timeout(const Duration(seconds: 30))) {
          // Après une erreur d'écriture on lit quand même la suite (sans
          // l'écrire) pour que l'émetteur reçoive bien la réponse d'erreur.
          if (writeError != null) continue;
          buf.add(d);
          if (buf.length >= 1 << 20) await flush();
        }
        await flush();
      } catch (_) {
        // Connexion coupée en plein morceau : on garde ce qui est arrivé,
        // l'émetteur reprendra à rf.offset.
        await flush();
      }
      if (writeError != null) {
        if (writeError is FormatException) return (400, {'error': 'too_much_data'});
        final r = writeErrorResponse(writeError!);
        if (r.$1 == 507) {
          s.job.error = 'Espace disque insuffisant.';
          s.failure = r;
        }
        return r;
      }
      return (200, {'offset': rf.offset});
    });
    try {
      await sendJson(req, result.$1, result.$2);
    } catch (_) {}
    if (result.$1 == 507) {
      await _endSession(s, TransferStatus.failed, error: 'Espace disque insuffisant dans ${s.receiveDir}.');
    }
  }

  Future<void> _finishFile(HttpRequest req, ReceiveSession s, ReceiveFile rf) async {
    final j = await readJsonBody(req);
    final expected = (j['sha256'] as String?)?.toLowerCase();
    if (rf.done) return sendJson(req, 200, {'ok': true, 'name': p.basename(rf.view.savedPath ?? '')});
    final res = await rf.locked<(int, Map<String, Object?>)>(() async {
      try {
        await rf.ensureOpen();
        if (rf.offset != rf.info.size) return (409, {'error': 'incomplete', 'offset': rf.offset});
        final digest = await rf.closeAndDigest();
        if (expected == null || digest != expected) {
          await rf.discardPart();
          rf.view.transferred = 0;
          return (422, {'error': 'integrity', 'offset': 0});
        }
        final path = await s.finalizeFile(rf, delegate.settings.duplicateMode);
        rf.view.savedPath = path;
        rf.view.transferred = rf.info.size;
        rf.view.status = TransferStatus.done;
        s.job.notify(force: true);
        unawaited(delegate.onFileSaved(path).catchError((_) {}));
        return (200, {'ok': true, 'name': p.basename(path)});
      } catch (e) {
        return writeErrorResponse(e);
      }
    });
    return sendJson(req, res.$1, res.$2);
  }

  /// Termine une session (fin normale si [status] est null).
  Future<void> _endSession(ReceiveSession s, TransferStatus? status, {String? error}) async {
    if (s.finished) return;
    s.finished = true;
    final cancelled = status == TransferStatus.cancelled;
    s.cancelled = cancelled || status == TransferStatus.failed;
    for (final rf in s.files.values) {
      if (rf.done || rf.skip) continue;
      rf.view.status = cancelled ? TransferStatus.cancelled : TransferStatus.failed;
    }
    // Annulation : on supprime les morceaux. Échec : on les garde pour reprendre.
    await s.closeAll(deleteParts: cancelled || s.failure?.$1 == 507);
    final job = s.job;
    if (status != null) {
      job.status = status;
      job.error = error;
    } else {
      job.status = job.failedCount > 0 || s.files.values.any((f) => !f.done && !f.skip)
          ? TransferStatus.failed
          : TransferStatus.done;
      if (job.status == TransferStatus.failed) {
        final n = s.files.values.where((f) => !f.done && !f.skip).length;
        final reason = s.files.values.map((f) => f.view.error).whereType<String>().firstOrNull;
        job.error ??= '$n fichier(s) non reçu(s).${reason != null ? ' Raison indiquée par ${s.from.name} : $reason' : ''}';
      }
    }
    job.notify(force: true);
    await delegate.onReceiveEnded(job);
    Future.delayed(const Duration(minutes: 10), () => sessions.remove(s.id));
  }

  // ------------------------------------------------- accès à distance
  Future<void> _tunnel(HttpRequest req, TrustedDevice dev, List<String> route) async {
    if (req.method == 'GET' && route.length == 2 && route[1] == 'wait') {
      final cmds = await delegate.tunnels.wait(dev.id);
      return sendJson(req, 200, {'commands': cmds});
    }
    if (req.method == 'POST' && route.length == 2 && route[1] == 'reply') {
      final j = await readJsonBody(req);
      delegate.tunnels.reply(dev.id, j['id'] as String, j['result'], j['error'] as String?);
      return sendJson(req, 200, {'ok': true});
    }
    return sendJson(req, 404, {'error': 'not_found'});
  }

  /// Chemin local demandé, via un partage (lecture) ou une offre.
  String _fsPath(Map<String, String> q, TrustedDevice dev) {
    final offer = q['offer'];
    if (offer != null) {
      final o = delegate.offers[offer];
      if (o == null || o.deviceId != dev.id) throw FsException('not_found', 'Proposition expirée.');
      final path = o.paths[q['file']];
      if (path == null) throw FsException('not_found', 'Fichier inconnu.');
      return path;
    }
    return delegate.fs.resolve(q['share'] ?? '', q['path'] ?? '');
  }

  Future<void> _fs(HttpRequest req, TrustedDevice dev, List<String> route) async {
    final q = req.uri.queryParameters;
    try {
      if (req.method == 'GET' && route.length == 2) {
        switch (route[1]) {
          case 'roots':
            return await sendJson(req, 200, {'roots': [for (final r in delegate.fs.roots()) r.toJson()]});
          case 'list':
            final l = await delegate.fs.list(q['share'] ?? '', q['path'] ?? '');
            return await sendJson(req, 200, {'entries': [for (final e in l) e.toJson()]});
          case 'walk':
            final w = await delegate.fs.walk(q['share'] ?? '', q['path'] ?? '');
            return await sendJson(req, 200, {
              'files': [for (final f in w) {'path': f.$1, 'size': f.$2, 'modified': f.$3.millisecondsSinceEpoch}],
            });
          case 'read':
            final path = _fsPath(q, dev);
            final offset = int.tryParse(q['offset'] ?? '') ?? 0;
            final len = (int.tryParse(q['len'] ?? '') ?? chunkSize).clamp(0, chunkSize);
            final data = await FsService.readRange(path, offset, len);
            _offerProgress(q, dev, offset + data.length);
            final r = req.response;
            r.statusCode = 200;
            r.headers.contentType = ContentType.binary;
            r.headers.set('x-file-size', '${await File(path).length()}');
            r.contentLength = data.length;
            r.add(data);
            return await r.close();
          case 'hash':
            final path = _fsPath(q, dev);
            return await sendJson(req, 200, {'sha256': await FsService.sha256Of(path)});
        }
      }
      if (req.method == 'POST' && route.length == 4 && route[1] == 'offer' && route[3] == 'done') {
        final j = await readJsonBody(req);
        final o = delegate.offers[route[2]];
        if (o != null && o.deviceId == dev.id) {
          final f = o.job.files.where((x) => x.fileId == j['fileId']).firstOrNull;
          if (f != null) {
            final ok = j['ok'] == true;
            f.status = ok ? TransferStatus.done : TransferStatus.failed;
            if (ok) f.transferred = f.size;
            f.error = j['error'] as String?;
          }
          if (j['finished'] == true) {
            o.job.status = o.job.files.every((x) => x.status == TransferStatus.done) ? TransferStatus.done : TransferStatus.failed;
            if (o.job.status == TransferStatus.failed) {
              o.job.error ??= (j['error'] as String?) ?? 'Certains fichiers n\'ont pas été téléchargés par ${dev.name}.';
            }
            delegate.offers.remove(o.token);
            o.job.notify(force: true);
            await delegate.onReceiveEnded(o.job);
          } else {
            o.job.notify(force: true);
          }
        }
        return await sendJson(req, 200, {'ok': true});
      }
      return await sendJson(req, 404, {'error': 'not_found'});
    } on FsException catch (e) {
      return sendJson(req, e.code == 'forbidden' ? 403 : 404, {'error': e.code, 'message': e.message});
    } on FileSystemException catch (e) {
      return sendJson(req, 500, {'error': 'read_failed', 'message': e.osError?.message ?? e.message});
    }
  }

  void _offerProgress(Map<String, String> q, TrustedDevice dev, int upTo) {
    final o = delegate.offers[q['offer']];
    if (o == null) return;
    final f = o.job.files.where((x) => x.fileId == q['file']).firstOrNull;
    if (f == null) return;
    f.status = TransferStatus.running;
    if (upTo > f.transferred) f.transferred = upTo;
    o.job.status = TransferStatus.running;
    o.job.speed.add(o.job.transferredBytes);
    o.job.notify();
  }

  /// Erreur lisible pour l'interface si le serveur n'a pas pu démarrer.
  static String describeBindError(Object e) {
    if (e is SocketException) {
      return 'Impossible d\'ouvrir le port réseau de Transferys : ${e.message}';
    }
    return describeNetworkError(e).message;
  }
}
