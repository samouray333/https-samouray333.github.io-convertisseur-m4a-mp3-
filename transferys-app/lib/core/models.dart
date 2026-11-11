// Modèles de données partagés par tous les modules de Transferys.
//
// Ce fichier ne dépend pas de Flutter : il est utilisé par le moteur
// (réseau, transfert) qui est testé en Dart pur.

/// Plateforme d'un appareil distant.
enum DevicePlatform { windows, android, linux, other }

DevicePlatform platformFromString(String? s) {
  switch (s) {
    case 'windows':
      return DevicePlatform.windows;
    case 'android':
      return DevicePlatform.android;
    case 'linux':
      return DevicePlatform.linux;
    default:
      return DevicePlatform.other;
  }
}

/// Appareil vu sur le réseau (découverte, QR code ou IP manuelle).
class Peer {
  Peer({
    required this.id,
    required this.name,
    required this.platform,
    required this.address,
    required this.port,
    this.fingerprint,
    DateTime? lastSeen,
  }) : lastSeen = lastSeen ?? DateTime.now();

  final String id;
  String name;
  DevicePlatform platform;
  String address;
  int port;

  /// Empreinte SHA-256 complète du certificat, si connue (QR code / /info).
  String? fingerprint;
  DateTime lastSeen;

  Uri baseUri() => Uri(scheme: 'https', host: address, port: port);

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'platform': platform.name,
        'address': address,
        'port': port,
        if (fingerprint != null) 'fingerprint': fingerprint,
      };
}

/// Appareil de confiance (appairé par PIN).
class TrustedDevice {
  TrustedDevice({
    required this.id,
    required this.name,
    required this.platform,
    required this.fingerprint,
    required this.secret,
    required this.pairedAt,
    this.lastAddress,
    this.lastPort,
    List<String>? remoteAddresses,
    this.remotePort,
  }) : remoteAddresses = remoteAddresses ?? [];

  final String id;
  String name;
  DevicePlatform platform;

  /// Adresses joignables depuis Internet (IPv6 globales, IPv4 de la box),
  /// apprises quand les deux appareils étaient sur le même réseau.
  List<String> remoteAddresses;
  int? remotePort;

  /// Empreinte SHA-256 du certificat TLS de cet appareil (épinglage).
  String fingerprint;

  /// Secret partagé (base64) établi pendant l'appairage, sert de jeton.
  String secret;
  DateTime pairedAt;
  String? lastAddress;
  int? lastPort;

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'platform': platform.name,
        'fingerprint': fingerprint,
        'secret': secret,
        'pairedAt': pairedAt.toIso8601String(),
        'lastAddress': lastAddress,
        'lastPort': lastPort,
        'remoteAddresses': remoteAddresses,
        'remotePort': remotePort,
      };

  factory TrustedDevice.fromJson(Map<String, dynamic> j) => TrustedDevice(
        id: j['id'] as String,
        name: j['name'] as String? ?? 'Appareil',
        platform: platformFromString(j['platform'] as String?),
        fingerprint: j['fingerprint'] as String,
        secret: j['secret'] as String,
        pairedAt: DateTime.tryParse(j['pairedAt'] as String? ?? '') ?? DateTime.now(),
        lastAddress: j['lastAddress'] as String?,
        lastPort: j['lastPort'] as int?,
        remoteAddresses: ((j['remoteAddresses'] as List?) ?? const []).cast<String>().toList(),
        remotePort: j['remotePort'] as int?,
      );
}

/// Sens d'un transfert.
enum TransferDirection { send, receive }

/// État d'un transfert (global ou par fichier).
enum TransferStatus {
  waiting, // en attente (acceptation, file d'attente)
  running,
  paused,
  reconnecting,
  done,
  skipped, // doublon ignoré
  cancelled,
  rejected,
  failed,
}

extension TransferStatusFr on TransferStatus {
  String get label {
    switch (this) {
      case TransferStatus.waiting:
        return 'En attente';
      case TransferStatus.running:
        return 'En cours';
      case TransferStatus.paused:
        return 'En pause';
      case TransferStatus.reconnecting:
        return 'Reconnexion…';
      case TransferStatus.done:
        return 'Terminé';
      case TransferStatus.skipped:
        return 'Ignoré (doublon)';
      case TransferStatus.cancelled:
        return 'Annulé';
      case TransferStatus.rejected:
        return 'Refusé';
      case TransferStatus.failed:
        return 'Échec';
    }
  }

  bool get isFinal =>
      this == TransferStatus.done ||
      this == TransferStatus.skipped ||
      this == TransferStatus.cancelled ||
      this == TransferStatus.rejected ||
      this == TransferStatus.failed;
}

/// Gestion des doublons à la réception.
enum DuplicateMode { rename, replace, skip }

DuplicateMode duplicateModeFromString(String? s) =>
    DuplicateMode.values.firstWhere((e) => e.name == s, orElse: () => DuplicateMode.rename);

/// Un fichier dans un transfert (vue UI, côté envoi ou réception).
class TransferFile {
  TransferFile({
    required this.fileId,
    required this.relPath,
    required this.size,
    this.status = TransferStatus.waiting,
  });

  final String fileId;
  final String relPath;
  final int size;
  int transferred = 0;
  TransferStatus status;
  String? error;

  /// Chemin final sur disque (côté réception).
  String? savedPath;

  double get progress => size == 0 ? (status == TransferStatus.done ? 1 : 0) : transferred / size;
}

/// Entrée d'historique.
class HistoryEntry {
  HistoryEntry({
    required this.id,
    required this.date,
    required this.direction,
    required this.peerName,
    required this.files,
    required this.totalSize,
    required this.status,
    this.folder,
    this.error,
  });

  final String id;
  final DateTime date;
  final TransferDirection direction;
  final String peerName;
  final List<HistoryFile> files;
  final int totalSize;
  final TransferStatus status;

  /// Dossier de réception (pour « Ouvrir le dossier »).
  final String? folder;
  final String? error;

  Map<String, dynamic> toJson() => {
        'id': id,
        'date': date.toIso8601String(),
        'direction': direction.name,
        'peerName': peerName,
        'files': files.map((f) => f.toJson()).toList(),
        'totalSize': totalSize,
        'status': status.name,
        'folder': folder,
        'error': error,
      };

  factory HistoryEntry.fromJson(Map<String, dynamic> j) => HistoryEntry(
        id: j['id'] as String,
        date: DateTime.tryParse(j['date'] as String? ?? '') ?? DateTime.now(),
        direction: j['direction'] == 'send' ? TransferDirection.send : TransferDirection.receive,
        peerName: j['peerName'] as String? ?? '',
        files: ((j['files'] as List?) ?? const [])
            .map((e) => HistoryFile.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        totalSize: (j['totalSize'] as num?)?.toInt() ?? 0,
        status: TransferStatus.values.firstWhere((s) => s.name == j['status'],
            orElse: () => TransferStatus.done),
        folder: j['folder'] as String?,
        error: j['error'] as String?,
      );
}

class HistoryFile {
  HistoryFile({required this.name, required this.size, required this.status, this.path});
  final String name;
  final int size;
  final TransferStatus status;
  final String? path;

  Map<String, dynamic> toJson() => {'name': name, 'size': size, 'status': status.name, 'path': path};

  factory HistoryFile.fromJson(Map<String, dynamic> j) => HistoryFile(
        name: j['name'] as String? ?? '',
        size: (j['size'] as num?)?.toInt() ?? 0,
        status: TransferStatus.values
            .firstWhere((s) => s.name == j['status'], orElse: () => TransferStatus.done),
        path: j['path'] as String?,
      );
}
