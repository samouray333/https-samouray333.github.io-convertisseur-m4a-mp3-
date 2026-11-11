// Découverte automatique des appareils sur le réseau local.
//
// Chaque appareil s'annonce en UDP (multicast 224.0.0.170 + broadcast sur
// chaque sous-réseau) toutes les 8 secondes, et répond directement (unicast)
// à toute annonce reçue. Le broadcast par interface couvre le cas du PC
// connecté au point d'accès du téléphone, où le multicast passe souvent mal.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../core/models.dart';
import 'net_utils.dart';

class DiscoveryAnnouncement {
  DiscoveryAnnouncement({
    required this.id,
    required this.name,
    required this.platform,
    required this.port,
    required this.fingerprint,
  });
  final String id;
  final String name;
  final DevicePlatform platform;
  final int port;
  final String fingerprint;
}

class Discovery {
  Discovery({
    required this.self,
    this.udpPort = defaultUdpPort,
    this.multicastGroup = defaultGroup,
    this.announceInterval = const Duration(seconds: 8),
    this.peerTimeout = const Duration(seconds: 30),
  });

  static const int defaultUdpPort = 53517;
  static const String defaultGroup = '224.0.0.170';
  static const String appTag = 'transferys';
  static const int protocolVersion = 1;

  /// Informations de cet appareil (mises à jour si le nom change).
  DiscoveryAnnouncement Function() self;
  final int udpPort;
  final String multicastGroup;
  final Duration announceInterval;
  final Duration peerTimeout;

  RawDatagramSocket? _socket;
  Timer? _timer;
  final _peers = <String, Peer>{};
  final _controller = StreamController<List<Peer>>.broadcast();
  String? lastError;

  /// Liste courante des appareils visibles (mise à jour en continu).
  Stream<List<Peer>> get peersStream => _controller.stream;
  List<Peer> get peers => _peers.values.toList();
  bool get running => _socket != null;

  Future<void> start() async {
    if (_socket != null) return;
    try {
      final s = await RawDatagramSocket.bind(InternetAddress.anyIPv4, udpPort, reuseAddress: true);
      s.broadcastEnabled = true;
      s.multicastLoopback = false;
      await _joinGroups(s);
      s.listen((ev) {
        if (ev == RawSocketEvent.read) {
          Datagram? d;
          while ((d = s.receive()) != null) {
            _onDatagram(d!);
          }
        }
      });
      _socket = s;
      lastError = null;
    } catch (e) {
      lastError = 'Découverte automatique indisponible (port UDP $udpPort occupé ou bloqué) : $e';
      return;
    }
    announce();
    _timer = Timer.periodic(announceInterval, (_) {
      announce();
      _expire();
    });
  }

  Future<void> _joinGroups(RawDatagramSocket s) async {
    final group = InternetAddress(multicastGroup);
    try {
      final ifaces = await NetworkInterface.list(type: InternetAddressType.IPv4);
      var joined = false;
      for (final ni in ifaces) {
        try {
          s.joinMulticast(group, ni);
          joined = true;
        } catch (_) {}
      }
      if (!joined) s.joinMulticast(group);
    } catch (_) {
      try {
        s.joinMulticast(group);
      } catch (_) {}
    }
  }

  Future<void> stop() async {
    _timer?.cancel();
    _timer = null;
    _socket?.close();
    _socket = null;
  }

  /// Redémarre (ex. changement de réseau Wi-Fi).
  Future<void> restart() async {
    await stop();
    await start();
  }

  List<int> _packet(String type) {
    final me = self();
    return utf8.encode(jsonEncode({
      'app': appTag,
      'v': protocolVersion,
      'type': type,
      'id': me.id,
      'name': me.name,
      'platform': me.platform.name,
      'port': me.port,
      'fp': me.fingerprint,
    }));
  }

  /// Envoie une annonce sur le multicast et sur chaque broadcast de sous-réseau.
  Future<void> announce() async {
    final s = _socket;
    if (s == null) return;
    final data = _packet('announce');
    final targets = <String>{multicastGroup, '255.255.255.255'};
    for (final l in await localIPv4Addresses()) {
      targets.add(broadcastFor(l.address.address));
    }
    for (final t in targets) {
      try {
        s.send(data, InternetAddress(t), udpPort);
      } catch (_) {}
    }
  }

  void _onDatagram(Datagram d) {
    try {
      final j = jsonDecode(utf8.decode(d.data));
      if (j is! Map || j['app'] != appTag) return;
      final id = j['id'] as String?;
      if (id == null || id == self().id) return;
      final peer = Peer(
        id: id,
        name: (j['name'] as String?) ?? 'Appareil',
        platform: platformFromString(j['platform'] as String?),
        address: d.address.address,
        port: (j['port'] as num?)?.toInt() ?? 53518,
        fingerprint: j['fp'] as String?,
      );
      final isNew = !_peers.containsKey(id);
      final old = _peers[id];
      _peers[id] = peer;
      if (j['type'] == 'announce') {
        // Réponse directe pour que l'autre nous voie immédiatement.
        try {
          _socket?.send(_packet('reply'), d.address, udpPort);
        } catch (_) {}
      }
      if (isNew || old?.name != peer.name || old?.address != peer.address || old?.port != peer.port) {
        _emit();
      }
    } catch (_) {
      // paquet étranger ou malformé : ignoré
    }
  }

  void _expire() {
    final now = DateTime.now();
    final before = _peers.length;
    _peers.removeWhere((_, p) => now.difference(p.lastSeen) > peerTimeout);
    if (_peers.length != before) _emit();
  }

  /// Ajoute un appareil trouvé autrement (QR code, IP manuelle).
  void addManual(Peer p) {
    _peers[p.id] = p;
    _emit();
  }

  Peer? find(String id) => _peers[id];

  /// Oublie un appareil (il réapparaîtra à sa prochaine annonce).
  void forget(String id) {
    if (_peers.remove(id) != null) _emit();
  }

  void _emit() {
    if (!_controller.isClosed) _controller.add(peers);
  }

  Future<void> dispose() async {
    await stop();
    await _controller.close();
  }
}
