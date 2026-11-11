// Abstraction du canal de transport.
//
// Version 1 : seul le Wi-Fi local (HTTPS + découverte UDP) est implémenté.
// Version 2 (prévue) : un BluetoothTransport pourra implémenter la même
// interface (découverte BLE + RFCOMM) pour les petits fichiers quand il n'y a
// pas de Wi-Fi. Le moteur choisira le transport via [TransportKind] ; les
// écrans, l'historique, l'appairage et la logique d'envoi par morceaux ne
// changeront pas.
import '../core/models.dart';

enum TransportKind { wifi, bluetooth }

abstract class Transport {
  TransportKind get kind;

  /// Nom affiché (« Wi-Fi », « Bluetooth »).
  String get label;

  /// Taille maximale conseillée pour un envoi (null = illimitée).
  int? get recommendedMaxBytes;
  bool get isRunning;

  Future<void> start();
  Future<void> stop();

  /// Appareils joignables par ce transport.
  Stream<List<Peer>> get peers;
}

/// Emplacement réservé pour la v2 : documente le contrat attendu.
class BluetoothTransportPlaceholder implements Transport {
  @override
  TransportKind get kind => TransportKind.bluetooth;
  @override
  String get label => 'Bluetooth (bientôt)';
  @override
  int? get recommendedMaxBytes => 50 * 1024 * 1024;
  @override
  bool get isRunning => false;
  @override
  Future<void> start() async {}
  @override
  Future<void> stop() async {}
  @override
  Stream<List<Peer>> get peers => const Stream.empty();
}
