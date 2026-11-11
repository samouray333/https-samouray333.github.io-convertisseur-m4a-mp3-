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
import 'network/upnp.dart';
import 'transfer/client.dart';
import 'transfer/downloader.dart';
import 'transfer/fs_service.dart';
import 'transfer/file_source.dart';
import 'transfer/job.dart';
import 'transfer/protocol.dart';
import 'transfer/receiver.dart';
import 'transfer/sender.dart';
import 'transfer/server.dart';
import 'transfer/tunnel.dart';
import 'transport/transport.dart';

const String appVersion = '1.1.1';

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

class RemoteStatus {
  bool checking = false;
  List<String> ipv6 = const [];
  String? publicIPv4;
  bool mapped = false;
  String? gateway;
  String? upnpError;

  bool get ipv4Usable => mapped && isPublicIPv4(publicIPv4);

  /// Adresses à communiquer aux appareils de confiance.
  List<String> get publicAddresses => [...ipv6, if (ipv4Usable) publicIPv4!];

  Map<String, Object?> toJson() => {
        'checking': checking,
        'ipv6': ipv6,
        'publicIPv4': publicIPv4,
        'mapped': mapped,
        'gateway': gateway,
        'upnpError': upnpError,
      };

  static RemoteStatus fromJson(Map j) => RemoteStatus()
    ..checking = j['checking'] as bool? ?? false
    ..ipv6 = ((j['ipv6'] as List?) ?? const []).cast<String>()
    ..publicIPv4 = j['publicIPv4'] as String?
    ..mapped = j['mapped'] as bool? ?? false
    ..gateway = j['gateway'] as String?
    ..upnpError = j['upnpError'] as String?;
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

  // ------------------------------------------------- accès à distance
  late final FsService _fs = FsService(() => _settings.shares);
  final _tunnels = TunnelHub();
  final _offers = <String, Offer>{};
  final _pushTokens = <String, DateTime>{}; // '$deviceId|$token' → expiration
  final _endpoints = <String, (String, int, DateTime)>{}; // deviceId → (hôte, port, date)
  final _remoteSync = <String, DateTime>{};
  final _upnp = UpnpClient();
  Timer? _remoteTimer;
  bool _tunnelsRunning = false;
  int _tunnelGeneration = 0;

  /// État de l'accès à distance de CET appareil (affiché dans les réglages).
  RemoteStatus remoteStatus = RemoteStatus();

  /// Appareils de confiance joignables hors du réseau local (via Internet).
  final remoteReachable = <String>{};

  bool get isDesktop => platform == DevicePlatform.windows || platform == DevicePlatform.linux;
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
    unawaited(applyRemoteSettings());
    _notify();
    return error;
  }

  Future<void> stop() async {
    _remoteTimer?.cancel();
    _tunnelGeneration++;
    // Referme le port ouvert sur la box quand l'appli s'arrête.
    if (remoteStatus.mapped) {
      await _upnp.closePort(port).timeout(const Duration(seconds: 3), onTimeout: () {});
      remoteStatus.mapped = false;
    }
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
    unawaited(applyRemoteSettings());
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

  /// Réponse donnée à un inconnu qui nous contacte depuis Internet : rien
  /// (ni nom d'appareil, ni identifiant).
  @override
  Map<String, dynamic> publicInfoJson() => {'app': 'transferys'};

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
        // L'autre appareil attend que son utilisateur clique « Autoriser ».
        final r3 = await c.json('POST', '/pair/confirm',
            body: {'pairId': pairId, 'code': typed, 'secret': secret}, timeout: const Duration(minutes: 3, seconds: 10));
        if (r3.error == 'refused') {
          throw TransferysException(ErrorCode.pairingFailed, 'Appairage refusé (ou non autorisé à temps) sur $name.');
        }
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

  /// Bouton « Autoriser » du dialogue d'appairage.
  void approvePairing(String pairId) => server.approveLocalPairing(pairId);

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
  /// [target] : dossier partagé de destination ({share, path}).
  TransferJob send(String deviceId, List<FileSource> sources, {Map<String, String>? target, String? token}) {
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
      sessionExtra: {if (target != null) 'target': target, if (token != null) 'token': token},
      resolveAddress: () async => (await resolve(t.id, fresh: true))?.$1,
      createClient: (host) => clientFor(t, host),
    );
    _startActivity();
    sj.run().whenComplete(() => _jobFinished(job));
    _notify();
    return job;
  }

  // ------------------------------------------------ résolution d'adresse
  PeerClient clientFor(TrustedDevice t, String host, {Duration connectTimeout = const Duration(seconds: 6)}) {
    final ep = _endpoints[t.id];
    final port = (ep != null && ep.$1 == host)
        ? ep.$2
        : (discovery.find(t.id)?.address == host
            ? discovery.find(t.id)!.port
            : (t.remoteAddresses.contains(host) ? (t.remotePort ?? t.lastPort) : t.lastPort) ?? Settings.defaultPort);
    return PeerClient(
      host: host,
      port: port,
      myId: _identity.id,
      expectedFingerprint: t.fingerprint,
      secret: t.secret,
      connectTimeout: connectTimeout,
    );
  }

  /// Trouve une adresse joignable pour un appareil de confiance : réseau local
  /// d'abord, puis adresses Internet apprises (IPv6, IPv4 de la box).
  Future<(String, int)?> resolve(String deviceId, {bool fresh = false}) async {
    final t = _trust.get(deviceId);
    if (t == null) return null;
    if (fresh) _endpoints.remove(deviceId);
    final cached = _endpoints[deviceId];
    if (cached != null && DateTime.now().difference(cached.$3) < const Duration(seconds: 20)) return (cached.$1, cached.$2);
    final cands = <(String, int, bool)>[]; // hôte, port, local ?
    final peer = discovery.find(deviceId);
    if (peer != null) cands.add((peer.address, peer.port, true));
    if (t.lastAddress != null && t.lastAddress != peer?.address) {
      cands.add((t.lastAddress!, t.lastPort ?? Settings.defaultPort, true));
    }
    for (final a in t.remoteAddresses) {
      cands.add((a, t.remotePort ?? t.lastPort ?? Settings.defaultPort, false));
    }
    if (cands.isEmpty) return null;
    final done = Completer<(String, int, bool)?>();
    var remaining = cands.length;
    for (final c in cands) {
      final client = PeerClient(
        host: c.$1,
        port: c.$2,
        myId: _identity.id,
        expectedFingerprint: t.fingerprint,
        secret: t.secret,
        connectTimeout: const Duration(seconds: 4),
      );
      client.json('GET', '/info', timeout: const Duration(seconds: 5)).then((r) {
        if (r.ok && r.body['id'] == deviceId && !done.isCompleted) done.complete(c);
      }).catchError((_) {}).whenComplete(() {
        client.close();
        remaining--;
        if (remaining == 0 && !done.isCompleted) done.complete(null);
      });
    }
    final found = await done.future;
    if (found == null) {
      _endpoints.remove(deviceId);
      if (remoteReachable.remove(deviceId)) _notify();
      return null;
    }
    _endpoints[deviceId] = (found.$1, found.$2, DateTime.now());
    final remote = !found.$3;
    if (remote ? remoteReachable.add(deviceId) : remoteReachable.remove(deviceId)) _notify();
    if (found.$3) unawaited(_syncRemoteInfo(t, found.$1));
    return (found.$1, found.$2);
  }

  /// Récupère les adresses Internet de l'appareil pendant qu'on est sur le
  /// même réseau, pour pouvoir le joindre plus tard en 4G.
  Future<void> _syncRemoteInfo(TrustedDevice t, String host) async {
    final last = _remoteSync[t.id];
    if (last != null && DateTime.now().difference(last) < const Duration(minutes: 10)) return;
    _remoteSync[t.id] = DateTime.now();
    final c = clientFor(t, host);
    try {
      final r = await c.json('GET', '/remote');
      if (!r.ok) return;
      final addrs = ((r.body['addresses'] as List?) ?? const []).cast<String>();
      t.remoteAddresses = addrs;
      t.remotePort = (r.body['port'] as num?)?.toInt();
      await _trust.put(t);
    } catch (_) {
    } finally {
      c.close();
    }
  }

  // --------------------------------------------- serveur : accès distant
  @override
  FsService get fs => _fs;
  @override
  TunnelHub get tunnels => _tunnels;
  @override
  Map<String, Offer> get offers => _offers;

  @override
  Future<Map<String, Object?>> remoteInfo() async => {
        'addresses': remoteStatus.publicAddresses,
        'port': port,
      };

  @override
  bool consumePushToken(String deviceId, String token) {
    _pushTokens.removeWhere((_, e) => DateTime.now().isAfter(e));
    final k = '$deviceId|$token';
    final exp = _pushTokens[k];
    if (exp == null || DateTime.now().isAfter(exp)) return false;
    return true; // valable pour toute la durée (plusieurs envois possibles)
  }

  /// Active / désactive l'accès à distance selon les réglages.
  Future<void> applyRemoteSettings() async {
    if (!_settings.remoteAccess) {
      _remoteTimer?.cancel();
      _remoteTimer = null;
      _tunnelGeneration++;
      _tunnelsRunning = false;
      if (remoteStatus.mapped) unawaited(_upnp.closePort(port));
      remoteStatus = RemoteStatus();
      await hooks.remoteMode(false);
      _notify();
      return;
    }
    if (_remoteTimer == null) {
      _remoteTimer = Timer.periodic(const Duration(minutes: 20), (_) => refreshRemote());
      await refreshRemote();
    }
    if (!isDesktop && !_tunnelsRunning) {
      _tunnelsRunning = true;
      await hooks.remoteMode(true);
      _startTunnels(++_tunnelGeneration);
    }
  }

  /// Ouvre le port sur la box (UPnP) et recense les adresses IPv6.
  Future<void> refreshRemote() async {
    final st = RemoteStatus()..checking = true;
    remoteStatus = st;
    _notify();
    st.ipv6 = await globalIPv6Addresses();
    if (isDesktop) {
      final locals = await localIPv4Addresses();
      if (locals.isNotEmpty) {
        final r = await _upnp.openPort(port: port, localIp: locals.first.address.address);
        st.publicIPv4 = r.externalIp;
        st.mapped = r.mapped;
        st.gateway = r.gatewayName;
        st.upnpError = r.error;
      } else {
        st.upnpError = 'Aucun réseau local.';
      }
    }
    st.checking = false;
    remoteStatus = st;
    _notify();
  }

  // ------------------------------------------ téléphone : canal inverse
  void _startTunnels(int gen) {
    final watched = <String>{};
    Future<void> loop(TrustedDevice t) async {
      var fails = 0;
      while (gen == _tunnelGeneration && _trust.get(t.id) != null) {
        final ep = await resolve(t.id);
        if (ep == null) {
          fails++;
          await Future.delayed(Duration(seconds: fails < 3 ? 10 : 30));
          continue;
        }
        final c = clientFor(t, ep.$1, connectTimeout: const Duration(seconds: 6));
        try {
          final r = await c.json('GET', '/tunnel/wait', timeout: const Duration(seconds: 40));
          fails = 0;
          if (!r.ok) {
            await Future.delayed(const Duration(seconds: 15));
            continue;
          }
          for (final cmd in ((r.body['commands'] as List?) ?? const [])) {
            unawaited(_runTunnelCommand(t, (cmd as Map).cast<String, Object?>(), ep.$1));
          }
        } catch (_) {
          _endpoints.remove(t.id);
          fails++;
          await Future.delayed(Duration(seconds: fails < 3 ? 5 : 20));
        } finally {
          c.close();
        }
      }
      watched.remove(t.id);
    }

    // Démarre une boucle par ordinateur de confiance (et pour les nouveaux).
    void scan() {
      if (gen != _tunnelGeneration) return;
      for (final t in _trust.all) {
        if (t.platform == DevicePlatform.android || watched.contains(t.id)) continue;
        watched.add(t.id);
        unawaited(loop(t));
      }
      Future.delayed(const Duration(seconds: 30), scan);
    }

    scan();
  }

  Future<void> _runTunnelCommand(TrustedDevice t, Map<String, Object?> cmd, String host) async {
    final id = cmd['id'] as String;
    final args = ((cmd['args'] as Map?) ?? const {}).cast<String, Object?>();
    Object? result;
    String? error;
    try {
      switch (cmd['op']) {
        case 'roots':
          result = [for (final r in _fs.roots()) r.toJson()];
        case 'list':
          final l = await _fs.list(args['share'] as String, args['path'] as String? ?? '');
          result = [for (final e in l) e.toJson()];
        case 'push':
          // Le PC demande des fichiers : on les lui envoie (il a fourni le jeton).
          final sources = await _sharedSources(args['share'] as String, (args['paths'] as List).cast<String>());
          send(t.id, sources, token: args['token'] as String?);
          result = {'started': true, 'files': sources.length};
        case 'pull':
          result = {'accepted': await _acceptOffer(t, args)};
        default:
          error = 'Commande inconnue';
      }
    } on FsException catch (e) {
      error = e.message;
    } on TransferysException catch (e) {
      error = e.message;
    } catch (e) {
      error = '$e';
    }
    final c = clientFor(t, host);
    try {
      await c.json('POST', '/tunnel/reply', body: {'id': id, 'result': result, 'error': error});
    } catch (_) {
    } finally {
      c.close();
    }
  }

  /// Fichiers d'un partage local (dossiers développés, arborescence gardée).
  Future<List<FileSource>> _sharedSources(String share, List<String> paths) async {
    final out = <FileSource>[];
    for (final rel in paths) {
      final full = _fs.resolve(share, rel);
      final parent = rel.contains('/') ? rel.substring(0, rel.lastIndexOf('/')) : '';
      if (FileSystemEntity.isDirectorySync(full)) {
        for (final f in await _fs.walk(share, rel)) {
          final r = parent.isEmpty ? f.$1 : f.$1.substring(parent.length + 1);
          out.add(LocalFileSource(_fs.resolve(share, f.$1), relPath: r, size: f.$2, modified: f.$3));
        }
      } else {
        out.add(LocalFileSource(full, relPath: rel.split('/').last));
      }
    }
    if (out.isEmpty) throw TransferysException(ErrorCode.protocol, 'Aucun fichier à envoyer (dossier vide).');
    return out;
  }

  /// Le PC propose des fichiers : on les télécharge depuis lui.
  Future<bool> _acceptOffer(TrustedDevice t, Map<String, Object?> args) async {
    final token = args['offer'] as String;
    final infos = (args['files'] as List).cast<Map>();
    final target = (args['target'] as Map?)?.cast<String, Object?>();
    var dest = _settings.receiveDir;
    if (target != null) {
      final share = target['share'] as String;
      if (!_fs.writable(share)) throw TransferysException(ErrorCode.permission, 'Ce dossier est en lecture seule.');
      dest = _fs.resolve(share, target['path'] as String? ?? '');
    } else if (_settings.confirmBeforeReceive) {
      final req = IncomingRequest(
        sessionId: token,
        from: t,
        files: [
          for (final f in infos)
            IncomingFileInfo(fileId: f['fileId'] as String, relPath: f['relPath'] as String, size: f['size'] as int, modified: null),
        ],
      );
      final ok = await confirmIncoming(req).timeout(TransferServer.decisionTimeout, onTimeout: () => false);
      if (!ok) return false;
    }
    final files = [
      for (final f in infos)
        RemoteFile(
          fileId: f['fileId'] as String,
          relPath: f['relPath'] as String,
          size: f['size'] as int,
          modified: f['modified'] is int ? DateTime.fromMillisecondsSinceEpoch(f['modified'] as int) : null,
          query: {'offer': token, 'file': f['fileId'] as String},
        ),
    ];
    _startDownload(t, files, dest, onFileDone: (rf, ok, err, finished) async {
      final host = _endpoints[t.id]?.$1 ?? (await resolve(t.id))?.$1;
      if (host == null) return;
      final c = clientFor(t, host);
      try {
        await c.json('POST', '/fs/offer/$token/done', body: {'fileId': rf.fileId, 'ok': ok, 'error': err, 'finished': finished});
      } finally {
        c.close();
      }
    });
    return true;
  }

  TransferJob _startDownload(TrustedDevice t, List<RemoteFile> files, String dest,
      {Future<void> Function(RemoteFile, bool, String?, bool)? onFileDone}) {
    final job = TransferJob(
      id: randomToken(12),
      direction: TransferDirection.receive,
      peerName: t.name,
      peerId: t.id,
      files: [for (final f in files) TransferFile(fileId: f.fileId, relPath: f.relPath, size: f.size)],
      folder: dest,
    );
    jobs.insert(0, job);
    job.changes.listen((_) => _notify());
    _startActivity();
    DownloadJob(
      job: job,
      files: files,
      destDir: dest,
      peerId: t.id,
      createClient: (h) => clientFor(t, h),
      resolveAddress: () async => (await resolve(t.id, fresh: true))?.$1,
      duplicateMode: _settings.duplicateMode,
      onFileSaved: hooks.fileSaved,
      onFileDone: onFileDone,
    ).run().whenComplete(() => _jobFinished(job));
    _notify();
    return job;
  }

  // ------------------------------------------ explorateur (côté demandeur)
  Future<T> _direct<T>(String deviceId, Future<T> Function(PeerClient c) f) async {
    final t = _trust.get(deviceId)!;
    final ep = await resolve(deviceId);
    if (ep == null) throw TransferysException(ErrorCode.unreachable, '${t.name} est injoignable.');
    final c = clientFor(t, ep.$1);
    try {
      return await f(c);
    } finally {
      c.close();
    }
  }

  bool _tunnelOnly(String deviceId) => _tunnels.isActive(deviceId);

  /// Joignable directement ? Sinon, canal inverse ?
  Future<bool> _directReachable(String deviceId) async => (await resolve(deviceId)) != null;

  Never _fsError(ApiResponse r, String name) {
    throw TransferysException(ErrorCode.permission, (r.body['message'] as String?) ?? 'Accès refusé par $name (${r.status}).');
  }

  Future<List<RemoteRoot>> remoteRoots(String deviceId) async {
    final t = _requireTrusted(deviceId);
    if (await _directReachable(deviceId)) {
      return _direct(deviceId, (c) async {
        final r = await c.json('GET', '/fs/roots');
        if (!r.ok) _fsError(r, t.name);
        return [for (final x in (r.body['roots'] as List)) RemoteRoot.fromJson(x as Map)];
      });
    }
    if (_tunnelOnly(deviceId)) {
      final r = await _tunnelCall(deviceId, 'roots', {});
      return [for (final x in (r as List)) RemoteRoot.fromJson(x as Map)];
    }
    throw _unreachable(t);
  }

  Future<List<RemoteEntry>> remoteList(String deviceId, String share, String path) async {
    final t = _requireTrusted(deviceId);
    if (await _directReachable(deviceId)) {
      return _direct(deviceId, (c) async {
        final r = await c.json('GET', '/fs/list', query: {'share': share, 'path': path});
        if (!r.ok) _fsError(r, t.name);
        return [for (final x in (r.body['entries'] as List)) RemoteEntry.fromJson(x as Map)];
      });
    }
    if (_tunnelOnly(deviceId)) {
      final r = await _tunnelCall(deviceId, 'list', {'share': share, 'path': path});
      return [for (final x in (r as List)) RemoteEntry.fromJson(x as Map)];
    }
    throw _unreachable(t);
  }

  /// Télécharge des fichiers / dossiers d'un partage distant.
  Future<void> download(String deviceId, String share, List<String> paths, {String? destDir}) async {
    final t = _requireTrusted(deviceId);
    if (await _directReachable(deviceId)) {
      final files = <RemoteFile>[];
      await _direct(deviceId, (c) async {
        for (final rel in paths) {
          final r = await c.json('GET', '/fs/walk', query: {'share': share, 'path': rel});
          if (!r.ok) _fsError(r, t.name);
          final parent = rel.contains('/') ? rel.substring(0, rel.lastIndexOf('/')) : '';
          for (final f in (r.body['files'] as List)) {
            final m = f as Map;
            final full = m['path'] as String;
            files.add(RemoteFile(
              fileId: '${files.length}',
              relPath: parent.isEmpty ? full : full.substring(parent.length + 1),
              size: m['size'] as int,
              modified: DateTime.fromMillisecondsSinceEpoch(m['modified'] as int),
              query: {'share': share, 'path': full},
            ));
          }
        }
      });
      if (files.isEmpty) throw TransferysException(ErrorCode.protocol, 'Rien à télécharger (dossier vide).');
      _startDownload(t, files, destDir ?? _settings.receiveDir);
      return;
    }
    if (_tunnelOnly(deviceId)) {
      // Le téléphone ne peut pas être joint : on lui demande de nous envoyer
      // les fichiers (réception acceptée d'office grâce au jeton).
      final token = randomToken(16);
      _pushTokens['$deviceId|$token'] = DateTime.now().add(const Duration(hours: 2));
      final r = await _tunnelCall(deviceId, 'push', {'share': share, 'paths': paths, 'token': token});
      if (r is Map && r['started'] != true) throw TransferysException(ErrorCode.protocol, 'Refusé par ${t.name}.');
      return;
    }
    throw _unreachable(t);
  }

  /// Envoie des fichiers dans un dossier partagé (en écriture) de l'autre
  /// appareil, ou dans son dossier de réception si [share] est null.
  Future<void> upload(String deviceId, List<FileSource> sources, {String? share, String path = ''}) async {
    final t = _requireTrusted(deviceId);
    final target = share == null ? null : {'share': share, 'path': path};
    if (await _directReachable(deviceId)) {
      send(deviceId, sources, target: target);
      return;
    }
    if (_tunnelOnly(deviceId)) {
      await _sendViaOffer(t, sources, target);
      return;
    }
    throw _unreachable(t);
  }

  /// Envoi « intelligent » utilisé par l'interface : direct si possible,
  /// sinon proposition via le canal inverse (téléphone en 4G).
  Future<void> sendSmart(String deviceId, List<FileSource> sources) => upload(deviceId, sources);

  Future<void> _sendViaOffer(TrustedDevice t, List<FileSource> sources, Map<String, String>? target) async {
    final token = randomToken(16);
    final paths = <String, String>{};
    for (var i = 0; i < sources.length; i++) {
      final s = sources[i];
      if (s is! LocalFileSource) throw TransferysException(ErrorCode.protocol, 'Source non prise en charge à distance.');
      paths['$i'] = s.path;
    }
    final job = TransferJob(
      id: token,
      direction: TransferDirection.send,
      peerName: t.name,
      peerId: t.id,
      files: [for (var i = 0; i < sources.length; i++) TransferFile(fileId: '$i', relPath: sources[i].relPath, size: sources[i].size)],
    );
    job.onCancel = () {
      _offers.remove(token);
      job.status = TransferStatus.cancelled;
      job.notify(force: true);
      _jobFinished(job);
    };
    _offers[token] = Offer(token: token, deviceId: t.id, paths: paths, job: job);
    jobs.insert(0, job);
    job.changes.listen((_) => _notify());
    _notify();
    try {
      final r = await _tunnelCall(t.id, 'pull', {
        'offer': token,
        'target': target,
        'files': [
          for (var i = 0; i < sources.length; i++)
            {
              'fileId': '$i',
              'relPath': sources[i].relPath,
              'size': sources[i].size,
              'modified': sources[i].modified.millisecondsSinceEpoch,
            }
        ],
      }, timeout: const Duration(minutes: 3));
      if (r is Map && r['accepted'] == true) {
        job.status = TransferStatus.running;
      } else {
        job.status = TransferStatus.rejected;
        job.error = '${t.name} a refusé le transfert.';
        _offers.remove(token);
        await _jobFinished(job);
      }
    } catch (e) {
      job.status = TransferStatus.failed;
      job.error = e is TunnelError ? e.message : '$e';
      _offers.remove(token);
      await _jobFinished(job);
    }
    job.notify(force: true);
  }

  Future<Object?> _tunnelCall(String deviceId, String op, Map<String, Object?> args,
      {Duration timeout = const Duration(seconds: 40)}) async {
    try {
      return await _tunnels.call(deviceId, op, args, timeout: timeout);
    } on TunnelError catch (e) {
      throw TransferysException(ErrorCode.unreachable, e.message);
    }
  }

  TrustedDevice _requireTrusted(String id) {
    final t = _trust.get(id);
    if (t == null) throw TransferysException(ErrorCode.notPaired, 'Cet appareil n\'est pas appairé.');
    return t;
  }

  TransferysException _unreachable(TrustedDevice t) => TransferysException(
        ErrorCode.unreachable,
        t.platform == DevicePlatform.android
            ? '${t.name} est injoignable. Sur le téléphone, activez Réglages > Accès à distance (et gardez Transferys ouvert en arrière-plan).'
            : '${t.name} est injoignable. Vérifiez que le PC est allumé avec Transferys ouvert, et que l\'accès à distance y est activé.',
      );

  /// L'appareil est-il joignable en ce moment (local, Internet ou canal) ?
  bool isReachable(String id) => discovery.find(id) != null || remoteReachable.contains(id) || _tunnels.isActive(id);

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
