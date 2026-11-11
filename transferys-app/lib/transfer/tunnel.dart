// Canal inverse pour l'accès à distance.
//
// Un téléphone en 4G ne peut pas recevoir de connexion (l'opérateur bloque
// tout ce qui entre). C'est donc lui qui appelle le PC et attend ses ordres
// (« long polling ») : lister un dossier, envoyer des fichiers au PC,
// télécharger des fichiers proposés par le PC. Les données elles-mêmes
// passent toujours par des connexions ouvertes par le téléphone.
import 'dart:async';
import 'dart:math';

import 'job.dart';

class _Peer {
  final queue = <Map<String, Object?>>[];
  Completer<void>? waiter;
  DateTime lastSeen = DateTime.fromMillisecondsSinceEpoch(0);
  final pending = <String, Completer<Object?>>{};
}

class TunnelError implements Exception {
  TunnelError(this.message);
  final String message;
  @override
  String toString() => message;
}

class TunnelHub {
  final _peers = <String, _Peer>{};
  final _rnd = Random.secure();

  _Peer _p(String id) => _peers.putIfAbsent(id, () => _Peer());

  /// L'appareil a-t-il un canal ouvert récemment ?
  bool isActive(String deviceId) {
    final p = _peers[deviceId];
    return p != null && DateTime.now().difference(p.lastSeen) < const Duration(seconds: 45);
  }

  /// Envoie un ordre à l'appareil et attend sa réponse.
  Future<Object?> call(String deviceId, String op, Map<String, Object?> args,
      {Duration timeout = const Duration(seconds: 40)}) {
    if (!isActive(deviceId)) {
      return Future.error(TunnelError('L\'appareil n\'est pas joignable à distance (accès à distance désactivé ou hors connexion).'));
    }
    final p = _p(deviceId);
    final id = '${DateTime.now().microsecondsSinceEpoch}-${_rnd.nextInt(1 << 30)}';
    final c = Completer<Object?>();
    p.pending[id] = c;
    p.queue.add({'id': id, 'op': op, 'args': args});
    p.waiter?.complete();
    p.waiter = null;
    return c.future.timeout(timeout, onTimeout: () {
      p.pending.remove(id);
      throw TunnelError('L\'appareil n\'a pas répondu à temps.');
    });
  }

  /// Appelé par l'appareil distant : renvoie les ordres en attente (ou une
  /// liste vide au bout de [hold]).
  Future<List<Map<String, Object?>>> wait(String deviceId, {Duration hold = const Duration(seconds: 25)}) async {
    final p = _p(deviceId);
    p.lastSeen = DateTime.now();
    if (p.queue.isEmpty) {
      p.waiter?.complete();
      final w = Completer<void>();
      p.waiter = w;
      await w.future.timeout(hold, onTimeout: () {});
      if (identical(p.waiter, w)) p.waiter = null;
    }
    p.lastSeen = DateTime.now();
    final out = List<Map<String, Object?>>.from(p.queue);
    p.queue.clear();
    return out;
  }

  void reply(String deviceId, String id, Object? result, String? error) {
    final c = _p(deviceId).pending.remove(id);
    if (c == null || c.isCompleted) return;
    if (error != null) {
      c.completeError(TunnelError(error));
    } else {
      c.complete(result);
    }
  }
}

/// Fichiers proposés à un appareil qui viendra les télécharger lui-même.
class Offer {
  Offer({required this.token, required this.deviceId, required this.paths, required this.job});
  final String token;
  final String deviceId;

  /// fileId → chemin local.
  final Map<String, String> paths;
  final TransferJob job;
  final DateTime created = DateTime.now();
}
