// Moteur de Transferys : relie identité, découverte, serveur, envois,
// appairage, historique. Aucune dépendance à Flutter (testable en Dart pur).
import 'dart:async';
import 'dart:io';

import 'core/errors.dart';
import 'core/models.dart';
import 'core/settings.dart';
import 'core/stores.dart';
import 'network/discovery.dart';
import 'network/net_utils.dart';
import 'platform/platform_hooks.dart';
import 'security/identity.dart';
import 'security/pairing.dart';
import 'transfer/client.dart';
import 'transfer/file_source.dart';
import 'transfer/job.dart';
import 'transfer/protocol.dart';
import 'transfer/receiver.dart';
import 'transfer/sender.dart';
import 'transfer/server.dart';
import 'transport/transport.dart';

const String appVersion = '1.0.1';

/// Transport Wi-Fi local (v1).
class WifiTransport implements Transport {
  WifiTransport(this.discovery);
  final Discovery discovery;
  @override
  TransportKind get kind => TransportKind.wifi;
  @override
  String get label => 'Wi-Fi';
  @override
  int? get recommendedMaxBytes => null;
  @override
  bool get isRunning => discovery.running;
  @override
  Future<void> start() => discovery.start();
  @override
  Future<void> stop() => discovery.stop();
  @override
  Stream<List<Peer>> get peers => discovery.peersStream;
}

class TransferysEngine implements ServerDelegate {
  TransferysEngine({
    required this.dataDir,
    required this.platform,
    required Settings defaults,
    PlatformHooks? hooks,
    this.udpPort = Discovery.defaultUdpPort,
    this.enableDiscovery = true,
  })  : hooks = hooks ?? DefaultPlatformHooks(),
        _defaults = defaults;

  final String dataDir;
  final DevicePlatform platform;
  final PlatformHooks hooks;
  final int udpPort;
  final bool enableDiscovery;
  final Settings _defaults;

  late Settings _settings;
  late SettingsStore _settingsStore;
  late DeviceIdentity _identity;
  late TrustStore _trust;
  late HistoryStore history;
  late Discovery discovery;
  late TransferServer server;
  late WifiTransport wifi;

  /// Transports disponibles (v2 : + Bluetooth).
  List<Transport> get transports => [wifi];

  final jobs = <TransferJob>[];
  final _changes = StreamController<void>.broadcast();
  Timer? _activityTimer;

  /// Notifie l'interface d'un changement (appareils, transferts, réglages).
  Stream<void> get changes => _changes.stream;

  // Rappels branchés par l'interface.
  Future<bool> Function(IncomingRequest r)? onIncoming;
  void Function(PairingPrompt p)? onPairingPrompt;
  void Function(String pairId, bool success, String? message)? onPairingClosed;
  void Function(TransferJob job)? onJobEnded;

  @override
  Settings get settings => _settings;
  @override
  DeviceIdentity get identity => _identity;
  @override
  TrustStore get trust => _trust;

  int get port => server.boundPort ?? _settings.port;

  Future<void> init() async {
    await Directory(dataDir).create(recursive: true);
    _settingsStore = SettingsStore(dataDir);
    _settings = await _settingsStore.load(_defaults);
    _identity = await DeviceIdentity.loadOrCreate(dataDir);
    _trust = TrustStore(dataDir);
    await _trust.load();
    history = HistoryStore(dataDir);
    await history.load();
    server = TransferServer(this);
    discovery = Discovery(
      udpPort: udpPort,
      self: () => DiscoveryAnnouncement(
        id: _identity.id,
        name: _settings.deviceName,
        platform: platform,
        port: port,
        fingerprint: _identity.fingerprint.substring(0, 16),
      ),
    );
    wifi = WifiTransport(discovery);
    discovery.peersStream.listen((_) => _notify());
  }

  /// Démarre le serveur et la découverte.
  Future<String?> start() async {
    String? error;
    try {
      await server.start(_settings.port);
    } catch (e) {
      error = TransferServer.describeBindError(e);
      server.lastError = error;
    }
    await hooks.networkStarted();
    if (enableDiscovery) {
      await discovery.start();
      error ??= discovery.lastError;
    }
    unawaited(purgeOldPartials(_settings.receiveDir).catchError((_) {}));
    _notify();
    return error;
  }

  Future<void> stop() async {
    await discovery.stop();
    await server.stop();
  }

  Future<void> dispose() async {
    await stop();
    await discovery.dispose();
    _activityTimer?.cancel();
    await _changes.close();
  }

  void _notify() {
    if (!_changes.isClosed) _changes.add(null);
  }

  Future<void> saveSettings() async {
    await _settingsStore.save(_settings);
    unawaited(discovery.announce());
    _notify();
  }

  // ---------------------------------------------------------------- infos
  @override
  Map<String, dynamic> infoJson() => {
        'app': 'transferys',
        'protocol': protocolVersion,
        'version': appVersion,
        'id': _identity.id,
        'name': _settings.deviceName,
        'platform': platform.name,
        'fingerprint': _identity.fingerprint,
        'port': port,
      };

  /// Appareils visibles + appareils de confiance (même hors ligne).
  List<(Peer?, TrustedDevice?)> devices() {
    final out = <(Peer?, TrustedDevice?)>[];
    final seen = <String>{};
    for (final p in discovery.peers) {
      out.add((p, _trust.get(p.id)));
      seen.add(p.id);
    }
    for (final t in _trust.all) {
      if (!seen.contains(t.id)) out.add((null, t));
    }
    return out;
  }

  /// Interroge un appareil à une adresse donnée (IP manuelle ou QR code).
  Future<Peer> probe(String host, int port, {String? expectedFingerprint}) async {
    final locals = await localIPv4Addresses();
    final loopback = host == '127.0.0.1' || host == 'localhost';
    if (locals.isEmpty && !loopback) {
      throw TransferysException(ErrorCode.offline,
          'Cet appareil n\'est connecté à aucun réseau Wi-Fi. Activez le Wi-Fi (ou le point d\'accès du téléphone) puis réessayez.');
    }
    final c = PeerClient(host: host, port: port, myId: _identity.id, expectedFingerprint: expectedFingerprint);
    try {
      final r = await c.json('GET', '/info', timeout: const Duration(seconds: 6));
      if (!r.ok || r.body['app'] != 'transferys') {
        throw TransferysException(ErrorCode.protocol, 'L\'appareil à l\'adresse $host n\'est pas un appareil Transferys.');
      }
      final fp = c.seenFingerprint;
      if (fp == null || fp != r.body['fingerprint']) {
        throw TransferysException(ErrorCode.certificateChanged, 'Identité de l\'appareil incohérente : connexion refusée par sécurité.');
      }
      final peer = Peer(
        id: r.body['id'] as String,
        name: r.body['name'] as String? ?? host,
        platform: platformFromString(r.body['platform'] as String?),
        address: host,
        port: (r.body['port'] as num?)?.toInt() ?? port,
        fingerprint: fp,
      );
      discovery.addManual(peer);
      final t = _trust.get(peer.id);
      if (t != null) {
        t.lastAddress = host;
        t.lastPort = peer.port;
      }
      return peer;
    } catch (e) {
      if (e is TransferysException) rethrow;
      final ex = describeNetworkError(e, peerName: host);
      if (!loopback && !sameSubnet(host, locals)) {
        throw TransferysException(ErrorCode.differentNetwork,
            'L\'adresse $host n\'est pas sur le même réseau que cet appareil (${locals.first.address.address}). Connectez les deux appareils au même Wi-Fi.');
      }
      throw ex;
    } finally {
      c.close();
    }
  }

  // -------------------------------------------------------------- appairage
  /// Appaire cet appareil (A) avec [peer] (B). [askCode] demande à
  /// l'utilisateur le code affiché sur B (null = annulé).
  Future<TrustedDevice> pair(Peer peer, Future<String?> Function(String peerName, String? error) askCode) async {
    final pinned = (peer.fingerprint != null && peer.fingerprint!.length == 64) ? peer.fingerprint : null;
    final c = PeerClient(host: peer.address, port: peer.port, myId: _identity.id, expectedFingerprint: pinned);
    String? pairId;
    try {
      final hello = await c.json('POST', '/pair/hello', body: {
        'id': _identity.id,
        'name': _settings.deviceName,
        'platform': platform.name,
        'fingerprint': _identity.fingerprint,
        'port': port,
      });
      if (hello.status == 409) {
        throw TransferysException(ErrorCode.pairingFailed, '${peer.name} est déjà en cours d\'appairage avec un autre appareil. Réessayez dans un instant.');
      }
      if (!hello.ok) throw TransferysException(ErrorCode.pairingFailed, 'Appairage refusé par ${peer.name}.');
      final fpB = c.seenFingerprint!;
      if (hello.body['fingerprint'] != fpB) {
        throw TransferysException(ErrorCode.pairingFailed, 'Identité incohérente de ${peer.name} : appairage annulé par sécurité.');
      }
      pairId = hello.body['pairId'] as String;
      final commit = hello.body['commit'] as String;
      final nonceA = randomToken(16);
      final r2 = await c.json('POST', '/pair/nonce', body: {'pairId': pairId, 'nonceA': nonceA});
      if (!r2.ok) throw TransferysException(ErrorCode.pairingFailed, 'Appairage interrompu par ${peer.name}.');
      final nonceB = r2.body['nonceB'] as String;
      if (commitment(nonceB) != commit) {
        throw TransferysException(ErrorCode.pairingFailed, 'Échec du contrôle de sécurité : appairage annulé.');
      }
      final expected = pairingCode(fingerprintA: _identity.fingerprint, fingerprintB: fpB, nonceA: nonceA, nonceB: nonceB);
      final name = hello.body['name'] as String? ?? peer.name;
      String? err;
      for (var attempt = 0; attempt < 3; attempt++) {
        final typed = (await askCode(name, err))?.replaceAll(RegExp(r'\D'), '');
        if (typed == null) {
          await c.json('POST', '/pair/cancel', body: {'pairId': pairId}).catchError((_) => ApiResponse(0, {}));
          throw TransferysException(ErrorCode.pairingFailed, 'Appairage annulé.');
        }
        if (!constantTimeEquals(typed, expected)) {
          err = 'Code incorrect (${2 - attempt} essai(s) restant(s)). Vérifiez le code affiché sur $name.';
          continue;
        }
        final secret = randomToken(32);
        final r3 = await c.json('POST', '/pair/confirm', body: {'pairId': pairId, 'code': typed, 'secret': secret});
        if (!r3.ok) {
          throw TransferysException(ErrorCode.pairingFailed, 'Appairage refusé par $name (${r3.error ?? r3.status}).');
        }
        final dev = TrustedDevice(
          id: hello.body['id'] as String,
          name: name,
          platform: platformFromString(hello.body['platform'] as String?),
          fingerprint: fpB,
          secret: secret,
          pairedAt: DateTime.now(),
          lastAddress: peer.address,
          lastPort: (hello.body['port'] as num?)?.toInt() ?? peer.port,
        );
        await _trust.put(dev);
        _notify();
        return dev;
      }
      await c.json('POST', '/pair/cancel', body: {'pairId': pairId}).catchError((_) => ApiResponse(0, {}));
      throw TransferysException(ErrorCode.pairingFailed,
          'Trois codes incorrects : appairage annulé. Si vous avez bien recopié le code, quelqu\'un tente peut-être d\'intercepter la connexion.');
    } catch (e) {
      if (e is TransferysException) rethrow;
      throw describeNetworkError(e, peerName: peer.name, peerWasVisible: discovery.find(peer.id) != null);
    } finally {
      c.close();
    }
  }

  Future<void> removeTrusted(String id) async {
    await _trust.remove(id);
    _notify();
  }

  Future<void> renameTrusted(String id, String name) async {
    final t = _trust.get(id);
    if (t == null) return;
    t.name = name;
    await _trust.put(t);
    _notify();
  }

  @override
  void showPairingCode(PairingPrompt prompt) => onPairingPrompt?.call(prompt);

  @override
  void closePairingCode(String pairId, {required bool success, String? message}) {
    onPairingClosed?.call(pairId, success, message);
    _notify();
  }

  // ------------------------------------------------------------------ envoi
  /// Envoie [sources] à l'appareil de confiance [deviceId].
  TransferJob send(String deviceId, List<FileSource> sources) {
    final t = _trust.get(deviceId);
    if (t == null) {
      throw TransferysException(ErrorCode.notPaired, 'Cet appareil n\'est pas encore appairé.');
    }
    if (sources.isEmpty) throw TransferysException(ErrorCode.protocol, 'Aucun fichier à envoyer.');
    final job = TransferJob(
      id: randomToken(12),
      direction: TransferDirection.send,
      peerName: t.name,
      peerId: t.id,
      files: [
        for (var i = 0; i < sources.length; i++) TransferFile(fileId: '$i', relPath: sources[i].relPath, size: sources[i].size),
      ],
    );
    jobs.insert(0, job);
    job.changes.listen((_) => _notify());
    final sj = SendJob(
      job: job,
      sources: sources,
      resolveAddress: () async {
        final p = discovery.find(t.id);
        return p?.address ?? t.lastAddress;
      },
      createClient: (host) => PeerClient(
        host: host,
        port: discovery.find(t.id)?.port ?? t.lastPort ?? Settings.defaultPort,
        myId: _identity.id,
        expectedFingerprint: t.fingerprint,
        secret: t.secret,
      ),
    );
    _startActivity();
    sj.run().whenComplete(() => _jobFinished(job));
    _notify();
    return job;
  }

  // -------------------------------------------------------------- réception
  @override
  Future<bool> confirmIncoming(IncomingRequest r) async {
    final cb = onIncoming;
    if (cb == null) return false;
    return cb(r);
  }

  @override
  Future<int?> freeSpace(String dir) => hooks.freeSpace(dir);

  @override
  Future<void> onFileSaved(String path) => hooks.fileSaved(path);

  @override
  void onReceiveStarted(TransferJob job) {
    jobs.removeWhere((j) => j.id == job.id);
    jobs.insert(0, job);
    job.changes.listen((_) => _notify());
    _startActivity();
    _notify();
  }

  @override
  Future<void> onReceiveEnded(TransferJob job) => _jobFinished(job);

  Future<void> _jobFinished(TransferJob job) async {
    final folder = job.direction == TransferDirection.receive ? job.folder : null;
    await history.add(HistoryEntry(
      id: job.id,
      date: DateTime.now(),
      direction: job.direction,
      peerName: job.peerName,
      files: [
        for (final f in job.files)
          HistoryFile(name: f.relPath, size: f.size, status: f.status, path: f.savedPath),
      ],
      totalSize: job.totalSize,
      status: job.status,
      folder: folder,
      error: job.error,
    ));
    onJobEnded?.call(job);
    _notify();
  }

  /// Retire de la liste les transferts terminés.
  void clearFinishedJobs() {
    jobs.removeWhere((j) => !j.isActive);
    _notify();
  }

  // ----------------------------------------- service Android (premier plan)
  void _startActivity() {
    if (_activityTimer != null) return;
    _pushActivity();
    _activityTimer = Timer.periodic(const Duration(seconds: 1), (_) => _pushActivity());
  }

  void _pushActivity() {
    final active = jobs.where((j) => j.isActive).toList();
    if (active.isEmpty) {
      _activityTimer?.cancel();
      _activityTimer = null;
      hooks.transferActivity(active: false);
      return;
    }
    final total = active.fold<int>(0, (a, j) => a + j.totalSize);
    final done = active.fold<int>(0, (a, j) => a + j.transferredBytes);
    final pct = total == 0 ? 0 : (done * 100 ~/ total);
    final j = active.first;
    final verb = j.direction == TransferDirection.send ? 'Envoi vers' : 'Réception depuis';
    final title = active.length > 1 ? '${active.length} transferts en cours' : '$verb ${j.peerName}';
    final text = j.status == TransferStatus.reconnecting
        ? 'Connexion perdue, reprise automatique…'
        : (j.status == TransferStatus.paused ? 'En pause' : '$pct % • ${j.doneCount}/${j.files.length} fichier(s)');
    hooks.transferActivity(active: true, title: title, text: text, percent: pct);
  }
}
