// Erreurs de Transferys, avec des messages clairs en français.
import 'dart:async';
import 'dart:io';

enum ErrorCode {
  offline, // pas de réseau local
  differentNetwork, // pas sur le même réseau
  unreachable, // l'appareil ne répond pas
  refused, // connexion refusée (appli fermée)
  firewall, // visible mais injoignable : pare-feu
  certificateChanged, // l'empreinte ne correspond plus
  notPaired,
  pairingFailed,
  rejected, // refusé par le destinataire
  cancelledByPeer,
  diskFull,
  integrity, // SHA-256 différent
  fileUnreadable,
  permission,
  timeout,
  protocol,
  unknown,
}

class TransferysException implements Exception {
  TransferysException(this.code, this.message, {this.details});
  final ErrorCode code;
  final String message;
  final Object? details;

  @override
  String toString() => message;
}

/// Vrai si l'erreur est réseau (donc on peut réessayer automatiquement).
bool isNetworkError(Object e) =>
    e is SocketException ||
    e is HttpException ||
    e is TimeoutException ||
    // Coupure pendant la poignée de main TLS (fréquent sous Windows quand
    // l'autre appareil ferme ou perd le Wi-Fi). Un certificat différent est
    // détecté avant, dans PeerClient, et converti en certificateChanged.
    e is TlsException ||
    (e is TransferysException &&
        (e.code == ErrorCode.unreachable ||
            e.code == ErrorCode.refused ||
            e.code == ErrorCode.timeout ||
            e.code == ErrorCode.offline ||
            e.code == ErrorCode.firewall));

/// Erreur système « disque plein » (Linux/Android : ENOSPC=28, Windows : 112 ou 39).
bool isDiskFull(Object e) {
  if (e is FileSystemException) {
    final c = e.osError?.errorCode;
    if (c == 28 || c == 112 || c == 39) return true;
    final m = (e.osError?.message ?? e.message).toLowerCase();
    return m.contains('no space') || m.contains('espace') || m.contains('disk full');
  }
  return false;
}

/// Traduit une exception réseau en message compréhensible.
TransferysException describeNetworkError(Object e, {String peerName = 'l\'appareil', bool peerWasVisible = false}) {
  if (e is TransferysException) return e;
  if (e is TlsException) {
    return TransferysException(ErrorCode.unreachable,
        'La connexion sécurisée avec $peerName a été interrompue. Vérifiez que Transferys est ouvert dessus et que le Wi-Fi fonctionne.',
        details: e);
  }
  if (e is SocketException) {
    final code = e.osError?.errorCode;
    final msg = (e.osError?.message ?? e.message).toLowerCase();
    // 111 (Linux/Android) / 10061 (Windows) : connexion refusée.
    if (code == 111 || code == 10061 || msg.contains('refused')) {
      return TransferysException(ErrorCode.refused,
          'Transferys ne semble pas ouvert sur $peerName. Ouvrez l\'appli sur l\'autre appareil puis réessayez.',
          details: e);
    }
    // 101 / 10051 : réseau inaccessible.
    if (code == 101 || code == 10051 || code == 113 || code == 10065 || msg.contains('unreachable')) {
      return TransferysException(ErrorCode.offline,
          'Réseau inaccessible : vérifiez que le Wi-Fi est activé et que les deux appareils sont sur le même réseau.',
          details: e);
    }
    if (peerWasVisible) {
      return TransferysException(ErrorCode.firewall,
          '$peerName est visible mais refuse la connexion. Sur PC, le pare-feu Windows bloque probablement Transferys : autorisez-le pour les réseaux privés.',
          details: e);
    }
    return TransferysException(ErrorCode.unreachable,
        '$peerName ne répond pas. Vérifiez qu\'il est allumé, que Transferys est ouvert et qu\'il est sur le même réseau Wi-Fi.',
        details: e);
  }
  if (e is TimeoutException) {
    return TransferysException(
        ErrorCode.timeout,
        peerWasVisible
            ? '$peerName ne répond pas à temps. Le pare-feu Windows bloque peut-être Transferys.'
            : '$peerName ne répond pas. Vérifiez qu\'il est sur le même réseau Wi-Fi.',
        details: e);
  }
  if (e is HttpException) {
    return TransferysException(ErrorCode.unreachable, 'La connexion avec $peerName a été interrompue.', details: e);
  }
  return TransferysException(ErrorCode.unknown, 'Erreur inattendue : $e', details: e);
}
