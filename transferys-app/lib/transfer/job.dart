// Un transfert vu par l'interface (envoi ou réception) : fichiers,
// progression, vitesse, temps restant, actions pause / reprise / annulation.
import 'dart:async';

import '../core/models.dart';

class SpeedMeter {
  final _samples = <(DateTime, int)>[];

  /// Fenêtre glissante de 4 secondes.
  void add(int totalBytes) {
    final now = DateTime.now();
    _samples.add((now, totalBytes));
    _samples.removeWhere((s) => now.difference(s.$1) > const Duration(seconds: 4));
  }

  double get bytesPerSecond {
    if (_samples.length < 2) return 0;
    final first = _samples.first, last = _samples.last;
    final ms = last.$1.difference(first.$1).inMilliseconds;
    if (ms < 300) return 0;
    return (last.$2 - first.$2) * 1000 / ms;
  }

  void reset() => _samples.clear();
}

class TransferJob {
  TransferJob({
    required this.id,
    required this.direction,
    required this.peerName,
    required this.peerId,
    required this.files,
    this.folder,
  }) : startedAt = DateTime.now();

  final String id;
  final TransferDirection direction;
  final String peerName;
  final String peerId;
  final List<TransferFile> files;
  final DateTime startedAt;

  /// Dossier de réception (côté réception).
  String? folder;
  TransferStatus status = TransferStatus.waiting;
  String? error;

  /// Pause demandée par l'autre appareil (affichage seulement).
  bool remotePaused = false;
  final speed = SpeedMeter();

  /// Valeurs reçues du moteur (copie affichée par l'interface).
  double? mirroredSpeed;
  Duration? mirroredEta;

  double get bytesPerSecond => mirroredSpeed ?? speed.bytesPerSecond;

  // Actions branchées par l'émetteur ou le récepteur.
  void Function()? onPause;
  void Function()? onResume;
  void Function()? onCancel;

  final _changes = StreamController<void>.broadcast();
  Stream<void> get changes => _changes.stream;
  DateTime _lastNotify = DateTime.fromMillisecondsSinceEpoch(0);

  int get totalSize => files.fold(0, (a, f) => a + f.size);
  int get transferredBytes => files.fold(0, (a, f) => a + f.transferred);
  double get progress => totalSize == 0 ? (status == TransferStatus.done ? 1 : 0) : transferredBytes / totalSize;
  int get doneCount => files.where((f) => f.status == TransferStatus.done).length;
  int get failedCount => files.where((f) => f.status == TransferStatus.failed).length;

  Duration? get eta {
    if (mirroredSpeed != null) return mirroredEta;
    final s = speed.bytesPerSecond;
    if (s <= 0 || status != TransferStatus.running) return null;
    return Duration(seconds: ((totalSize - transferredBytes) / s).ceil());
  }

  TransferFile? get currentFile {
    for (final f in files) {
      if (f.status == TransferStatus.running || f.status == TransferStatus.reconnecting) return f;
    }
    return null;
  }

  bool get isActive => !status.isFinal;

  void pause() => onPause?.call();
  void resume() => onResume?.call();
  void cancel() => onCancel?.call();

  /// Notifie l'interface (limité à ~10 fois par seconde sauf si [force]).
  void notify({bool force = false}) {
    final now = DateTime.now();
    if (!force && now.difference(_lastNotify) < const Duration(milliseconds: 100)) return;
    _lastNotify = now;
    if (!_changes.isClosed) _changes.add(null);
  }

  void dispose() => _changes.close();

  // ------------------------------------------- copie moteur → interface
  Map<String, Object?> toJson() => {
        'id': id,
        'direction': direction.name,
        'peerName': peerName,
        'peerId': peerId,
        'folder': folder,
        'status': status.name,
        'error': error,
        'remotePaused': remotePaused,
        'speed': speed.bytesPerSecond,
        'eta': eta?.inSeconds,
        'files': [
          for (final f in files)
            [f.fileId, f.relPath, f.size, f.transferred, f.status.index, f.error, f.savedPath],
        ],
      };

  static TransferJob fromJson(Map j) {
    final job = TransferJob(
      id: j['id'] as String,
      direction: j['direction'] == 'send' ? TransferDirection.send : TransferDirection.receive,
      peerName: j['peerName'] as String,
      peerId: j['peerId'] as String,
      files: [
        for (final f in (j['files'] as List))
          TransferFile(fileId: (f as List)[0] as String, relPath: f[1] as String, size: f[2] as int),
      ],
    );
    job.applyJson(j);
    return job;
  }

  void applyJson(Map j) {
    folder = j['folder'] as String?;
    status = TransferStatus.values.byName(j['status'] as String);
    error = j['error'] as String?;
    remotePaused = j['remotePaused'] as bool? ?? false;
    mirroredSpeed = (j['speed'] as num?)?.toDouble() ?? 0;
    final e = j['eta'] as int?;
    mirroredEta = e == null ? null : Duration(seconds: e);
    final list = j['files'] as List;
    for (var i = 0; i < list.length && i < files.length; i++) {
      final f = list[i] as List;
      files[i]
        ..transferred = f[3] as int
        ..status = TransferStatus.values[f[4] as int]
        ..error = f[5] as String?
        ..savedPath = f[6] as String?;
    }
  }
}
