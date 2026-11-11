// Le moteur tourne dans un isolate dédié (un autre cœur du processeur) :
// le fil de l'interface Flutter ne traite jamais les octets transférés.
// Mesuré : 2,8 Mo/s si le réseau partage le fil de l'interface, 50 Mo/s
// dans un isolate séparé (même machine, même fichier).
//
// Ce fichier contient le côté « isolate » : il reçoit des commandes de
// l'interface et lui renvoie des instantanés d'état et des événements.
// Il n'utilise jamais Flutter ni les canaux de plateforme : tout ce qui est
// natif (espace disque Android, galerie, service au premier plan, lecture des
// content://) est demandé à l'interface via [_ProxyHooks].
import 'dart:async';
import 'dart:io';
import 'dart:isolate';

import '../core/errors.dart';
import '../core/models.dart';
import '../core/settings.dart';
import '../engine.dart';
import '../platform/platform_hooks.dart';
import '../transfer/fd_reader.dart';
import '../transfer/file_source.dart';
import '../transfer/receiver.dart';
import '../transfer/server.dart';

typedef _Request = Future<Object?> Function(String kind, Object? data);

class _ProxyHooks extends PlatformHooks {
  _ProxyHooks(this._req, this._notify);
  final _Request _req;
  final void Function(String kind, Object? data) _notify;

  @override
  Future<int?> freeSpace(String dir) async {
    final v = await _req('freeSpace', dir);
    return v is int ? v : null;
  }

  @override
  Future<void> fileSaved(String path) async => _notify('fileSaved', path);

  @override
  Future<void> transferActivity({required bool active, String? title, String? text, int? percent}) async =>
      _notify('activity', {'active': active, 'title': title, 'text': text, 'percent': percent});

  @override
  Future<void> networkStarted() async => _notify('networkStarted', null);

  @override
  Future<void> remoteMode(bool active) async => _notify('remoteMode', active);
}

/// Fichier Android lu via un descripteur ouvert par le fil principal.
class _FdFileSource extends FileSource {
  _FdFileSource(this.uri, this.relPath, this.size, this.modified, this._req);
  final String uri;
  @override
  final String relPath;
  @override
  final int size;
  @override
  final DateTime modified;
  final _Request _req;

  @override
  Future<SourceReader> open() async {
    final fd = await _req('openFd', uri);
    if (fd is! int || fd < 0) {
      throw const FileSystemException('Android refuse l\'accès à ce fichier (autorisation retirée ou fichier supprimé)');
    }
    // Lecture directe du descripteur (pas de réouverture par chemin).
    return FdReader(fd);
  }
}

Map<String, Object?> peerJson(Peer p) => p.toJson();

Peer peerFromJson(Map j) => Peer(
      id: j['id'] as String,
      name: j['name'] as String,
      platform: platformFromString(j['platform'] as String?),
      address: j['address'] as String,
      port: j['port'] as int,
      fingerprint: j['fingerprint'] as String?,
    );

Map<String, Object?> trustedJson(TrustedDevice t) => t.toJson()..remove('secret');

TrustedDevice trustedFromJson(Map j) =>
    TrustedDevice.fromJson({...j.cast<String, dynamic>(), 'secret': ''});

/// Point d'entrée de l'isolate moteur.
Future<void> engineWorkerMain(List<Object?> args) async {
  final toUi = args[0] as SendPort;
  final init = (args[1] as Map).cast<String, Object?>();
  final inbox = ReceivePort();
  toUi.send(['port', inbox.sendPort]);

  final pending = <int, Completer<Object?>>{};
  var nextId = 1;
  Future<Object?> request(String kind, Object? data) {
    final id = nextId++;
    final c = Completer<Object?>();
    pending[id] = c;
    toUi.send(['req', id, kind, data]);
    return c.future;
  }

  void notify(String kind, Object? data) => toUi.send(['evt', kind, data]);

  final defaults = Settings.fromJson(
    (init['defaults'] as Map).cast<String, dynamic>(),
    Settings(deviceName: 'Transferys', receiveDir: '.'),
  );
  final engine = TransferysEngine(
    dataDir: init['dataDir'] as String,
    platform: platformFromString(init['platform'] as String),
    defaults: defaults,
    hooks: _ProxyHooks(request, notify),
  );
  await engine.init();

  engine.onIncoming = (IncomingRequest r) async {
    final res = await request('incoming', {
      'sessionId': r.sessionId,
      'from': trustedJson(r.from),
      'files': [
        for (final f in r.files) {'fileId': f.fileId, 'relPath': f.relPath, 'size': f.size},
      ],
    });
    return res == true;
  };
  engine.onPairingPrompt = (PairingPrompt p) => notify('pairingPrompt', {
        'pairId': p.pairId,
        'peerName': p.peerName,
        'platform': p.platform.name,
        'code': p.code,
      });
  engine.onPairingClosed = (id, ok, msg) => notify('pairingClosed', {'pairId': id, 'success': ok, 'message': msg});
  engine.onJobEnded = (job) => notify('jobEnded', job.toJson());

  // ------------------------------------------------ instantanés d'état
  var lastHistoryKey = '';
  Timer? pendingSnap;
  void snapshot() {
    pendingSnap = null;
    final h = engine.history.entries;
    final hKey = '${h.length}:${h.isEmpty ? '' : h.first.id}';
    toUi.send([
      'snap',
      {
        'settings': engine.settings.toJson(),
        'port': engine.port,
        'discoveryRunning': engine.discovery.running,
        'discoveryError': engine.discovery.lastError,
        'devices': [
          for (final d in engine.devices())
            {'peer': d.$1 == null ? null : peerJson(d.$1!), 'trusted': d.$2 == null ? null : trustedJson(d.$2!)},
        ],
        'reachable': [for (final t in engine.trust.all) if (engine.isReachable(t.id)) t.id],
        'remoteStatus': engine.remoteStatus.toJson(),
        'trusted': [for (final t in engine.trust.all) trustedJson(t)],
        'jobs': [for (final j in engine.jobs) j.toJson()],
        if (hKey != lastHistoryKey) 'history': [for (final e in h) e.toJson()],
      }
    ]);
    lastHistoryKey = hKey;
  }

  void scheduleSnap() {
    pendingSnap ??= Timer(const Duration(milliseconds: 120), snapshot);
  }

  engine.changes.listen((_) => scheduleSnap());
  // Pendant un transfert : vitesse et temps restant rafraîchis 4 fois/s.
  Timer.periodic(const Duration(milliseconds: 250), (_) {
    if (engine.jobs.any((j) => j.isActive)) scheduleSnap();
  });

  final startError = await engine.start();
  toUi.send([
    'ready',
    {
      'id': engine.identity.id,
      'fingerprint': engine.identity.fingerprint,
      'startError': startError,
    }
  ]);
  snapshot();

  // ------------------------------------------------------ commandes
  Future<Object?> handle(String name, Object? data) async {
    final m = data is Map ? data.cast<String, Object?>() : const <String, Object?>{};
    switch (name) {
      case 'saveSettings':
        final s = Settings.fromJson((m['settings'] as Map).cast<String, dynamic>(), engine.settings);
        final old = engine.settings;
        old
          ..deviceName = s.deviceName
          ..receiveDir = s.receiveDir
          ..themeMode = s.themeMode
          ..confirmBeforeReceive = s.confirmBeforeReceive
          ..duplicateMode = s.duplicateMode
          ..autoStart = s.autoStart
          ..minimizeToTray = s.minimizeToTray
          ..explorerMenu = s.explorerMenu
          ..onboardingDone = s.onboardingDone
          ..remoteAccess = s.remoteAccess
          ..shares = s.shares;
        await engine.saveSettings();
        return null;
      case 'probe':
        final p = await engine.probe(m['host'] as String, m['port'] as int, expectedFingerprint: m['fingerprint'] as String?);
        return peerJson(p);
      case 'pair':
        final peer = peerFromJson(m['peer'] as Map);
        final t = await engine.pair(peer, (name, err) async {
          final r = await request('askCode', {'peerName': name, 'error': err});
          return r as String?;
        });
        return trustedJson(t);
      case 'send':
        final sources = <FileSource>[];
        for (final raw in (m['sources'] as List)) {
          final s = (raw as Map).cast<String, Object?>();
          final mod = DateTime.fromMillisecondsSinceEpoch(s['modified'] as int);
          if (s['uri'] != null) {
            sources.add(_FdFileSource(s['uri'] as String, s['relPath'] as String, s['size'] as int, mod, request));
          } else {
            sources.add(LocalFileSource(s['path'] as String,
                relPath: s['relPath'] as String, size: s['size'] as int, modified: mod));
          }
        }
        if (m['share'] != null || m['smart'] == true) {
          await engine.upload(m['deviceId'] as String, sources, share: m['share'] as String?, path: (m['path'] as String?) ?? '');
          return null;
        }
        final job = engine.send(m['deviceId'] as String, sources);
        return job.id;
      case 'roots':
        return [for (final r in await engine.remoteRoots(m['deviceId'] as String)) r.toJson()];
      case 'list':
        return [
          for (final e in await engine.remoteList(m['deviceId'] as String, m['share'] as String, m['path'] as String))
            e.toJson()
        ];
      case 'download':
        await engine.download(m['deviceId'] as String, m['share'] as String, (m['paths'] as List).cast<String>());
        return null;
      case 'refreshRemote':
        await engine.refreshRemote();
        return null;
      case 'job':
        final j = engine.jobs.where((x) => x.id == m['id']).firstOrNull;
        switch (m['action']) {
          case 'pause':
            j?.pause();
          case 'resume':
            j?.resume();
          case 'cancel':
            j?.cancel();
        }
        return null;
      case 'clearFinished':
        engine.clearFinishedJobs();
        return null;
      case 'clearHistory':
        await engine.history.clear();
        scheduleSnap();
        return null;
      case 'removeTrusted':
        await engine.removeTrusted(m['id'] as String);
        return null;
      case 'cancelLocalPairing':
        engine.server.cancelLocalPairing();
        return null;
      case 'resolveAll':
        await Future.wait([for (final t in engine.trust.all) engine.resolve(t.id)]);
        scheduleSnap();
        return null;
      case 'discovery':
        switch (m['action']) {
          case 'restart':
            await engine.discovery.restart();
          default:
            if (!engine.discovery.running) await engine.discovery.start();
            await engine.discovery.announce();
        }
        scheduleSnap();
        return null;
      case 'stop':
        await engine.stop();
        return null;
    }
    throw StateError('Commande inconnue : $name');
  }

  inbox.listen((msg) async {
    final l = msg as List;
    if (l[0] == 'res') {
      pending.remove(l[1] as int)?.complete(l[2]);
      return;
    }
    if (l[0] == 'cmd') {
      final id = l[1] as int;
      try {
        final r = await handle(l[2] as String, l[3]);
        toUi.send(['res', id, r, null]);
      } on TransferysException catch (e) {
        toUi.send(['res', id, null, {'code': e.code.name, 'message': e.message}]);
      } catch (e) {
        toUi.send(['res', id, null, {'code': 'unknown', 'message': '$e'}]);
      }
    }
  });
}
