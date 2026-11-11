// Côté interface : pilote le moteur qui tourne dans son isolate dédié et
// garde une copie de son état (appareils, transferts, historique) pour
// l'affichage. Les appels natifs demandés par le moteur (espace disque,
// galerie, service Android, lecture des content://) sont exécutés ici.
import 'dart:async';
import 'dart:isolate';

import '../core/errors.dart';
import '../core/models.dart';
import '../core/settings.dart';
import '../platform/android_bridge.dart';
import '../engine.dart' show RemoteStatus;
import '../platform/platform_hooks.dart';
import '../transfer/fs_service.dart';
import '../transfer/file_source.dart';
import '../transfer/job.dart';
import '../transfer/receiver.dart';
import '../transfer/server.dart';
import 'engine_worker.dart';

class IdentityInfo {
  IdentityInfo(this.id, this.fingerprint);
  final String id;
  final String fingerprint;
}

class HistoryView {
  HistoryView(this._proxy);
  final EngineProxy _proxy;
  List<HistoryEntry> entries = const [];
  Future<void> clear() async {
    entries = const [];
    await _proxy._cmd('clearHistory', null);
  }
}

class TrustView {
  List<TrustedDevice> all = const [];
  TrustedDevice? get(String id) => all.where((t) => t.id == id).firstOrNull;
}

class EngineProxy {
  EngineProxy({required this.platform, required this.hooks});
  final DevicePlatform platform;
  final PlatformHooks hooks;

  late SendPort _toWorker;
  final _fromWorker = ReceivePort();
  final _pending = <int, Completer<Object?>>{};
  var _nextId = 1;
  final _ready = Completer<void>();
  final _changes = StreamController<void>.broadcast();

  late IdentityInfo identity;
  String? startError;
  late Settings settings;
  int port = Settings.defaultPort;
  bool discoveryRunning = false;
  String? discoveryError;
  List<(Peer?, TrustedDevice?)> _devices = const [];
  Set<String> reachable = const {};
  RemoteStatus remoteStatus = RemoteStatus();
  final trust = TrustView();
  late final history = HistoryView(this);
  final jobs = <TransferJob>[];
  final _jobById = <String, TransferJob>{};

  Future<bool> Function(IncomingRequest r)? onIncoming;
  void Function(PairingPrompt p)? onPairingPrompt;
  void Function(String pairId, bool success, String? message)? onPairingClosed;
  void Function(TransferJob job)? onJobEnded;
  Future<String?> Function(String peerName, String? error)? _askCode;

  Stream<void> get changes => _changes.stream;
  List<(Peer?, TrustedDevice?)> devices() => _devices;
  bool isOnline(String id) => _devices.any((d) => d.$1?.id == id) || reachable.contains(id);

  /// Démarre l'isolate moteur et attend son premier état.
  Future<void> start({required String dataDir, required Settings defaults}) async {
    settings = defaults;
    _fromWorker.listen(_onMessage);
    await Isolate.spawn(
      engineWorkerMain,
      [
        _fromWorker.sendPort,
        {'dataDir': dataDir, 'platform': platform.name, 'defaults': defaults.toJson()},
      ],
      debugName: 'transferys-engine',
      errorsAreFatal: false,
    );
    await _ready.future;
  }

  Future<Object?> _cmd(String name, Object? data) async {
    final id = _nextId++;
    final c = Completer<Object?>();
    _pending[id] = c;
    _toWorker.send(['cmd', id, name, data]);
    return c.future;
  }

  void _emit() {
    if (!_changes.isClosed) _changes.add(null);
  }

  Future<void> _onMessage(dynamic msg) async {
    final l = msg as List;
    switch (l[0]) {
      case 'port':
        _toWorker = l[1] as SendPort;
      case 'ready':
        final m = l[1] as Map;
        identity = IdentityInfo(m['id'] as String, m['fingerprint'] as String);
        startError = m['startError'] as String?;
      case 'snap':
        _applySnapshot(l[1] as Map);
        if (!_ready.isCompleted) _ready.complete();
        _emit();
      case 'res':
        final c = _pending.remove(l[1] as int);
        final err = l[3] as Map?;
        if (c == null) return;
        if (err != null) {
          final code = ErrorCode.values.where((e) => e.name == err['code']).firstOrNull ?? ErrorCode.unknown;
          c.completeError(TransferysException(code, err['message'] as String));
        } else {
          c.complete(l[2]);
        }
      case 'req':
        final id = l[1] as int;
        Object? res;
        try {
          res = await _answer(l[2] as String, l[3]);
        } catch (_) {
          res = null;
        }
        _toWorker.send(['res', id, res]);
      case 'evt':
        _onEvent(l[1] as String, l[2]);
    }
  }

  void _applySnapshot(Map s) {
    settings = Settings.fromJson((s['settings'] as Map).cast<String, dynamic>(), settings);
    port = s['port'] as int;
    discoveryRunning = s['discoveryRunning'] as bool;
    discoveryError = s['discoveryError'] as String?;
    _devices = [
      for (final d in (s['devices'] as List))
        (
          (d as Map)['peer'] == null ? null : peerFromJson(d['peer'] as Map),
          d['trusted'] == null ? null : trustedFromJson(d['trusted'] as Map),
        ),
    ];
    trust.all = [for (final t in (s['trusted'] as List)) trustedFromJson(t as Map)];
    reachable = ((s['reachable'] as List?) ?? const []).cast<String>().toSet();
    if (s['remoteStatus'] is Map) remoteStatus = RemoteStatus.fromJson(s['remoteStatus'] as Map);
    final js = s['jobs'] as List;
    final seen = <String>{};
    jobs.clear();
    for (final raw in js) {
      final j = raw as Map;
      final id = j['id'] as String;
      seen.add(id);
      var job = _jobById[id];
      if (job == null) {
        job = TransferJob.fromJson(j);
        _wire(job);
        _jobById[id] = job;
      } else {
        job.applyJson(j);
      }
      jobs.add(job);
    }
    _jobById.removeWhere((k, _) => !seen.contains(k));
    if (s.containsKey('history')) {
      history.entries = [
        for (final e in (s['history'] as List)) HistoryEntry.fromJson((e as Map).cast<String, dynamic>()),
      ];
    }
  }

  void _wire(TransferJob job) {
    job.onPause = () => _cmd('job', {'id': job.id, 'action': 'pause'});
    job.onResume = () => _cmd('job', {'id': job.id, 'action': 'resume'});
    job.onCancel = () => _cmd('job', {'id': job.id, 'action': 'cancel'});
  }

  Future<Object?> _answer(String kind, Object? data) async {
    switch (kind) {
      case 'incoming':
        final m = data as Map;
        final from = trustedFromJson(m['from'] as Map);
        final req = IncomingRequest(
          sessionId: m['sessionId'] as String,
          from: from,
          files: [
            for (final f in (m['files'] as List))
              IncomingFileInfo(
                fileId: (f as Map)['fileId'] as String,
                relPath: f['relPath'] as String,
                size: f['size'] as int,
                modified: null,
              ),
          ],
        );
        final cb = onIncoming;
        return cb == null ? false : await cb(req);
      case 'askCode':
        final m = data as Map;
        final cb = _askCode;
        return cb == null ? null : await cb(m['peerName'] as String, m['error'] as String?);
      case 'freeSpace':
        return hooks.freeSpace(data as String);
      case 'openFd':
        return AndroidBridge.openFdRaw(data as String);
      case 'closeFd':
        await AndroidBridge.closeFdRaw(data as int);
        return null;
    }
    return null;
  }

  void _onEvent(String kind, Object? data) {
    switch (kind) {
      case 'fileSaved':
        hooks.fileSaved(data as String);
      case 'activity':
        final m = data as Map;
        hooks.transferActivity(
          active: m['active'] as bool,
          title: m['title'] as String?,
          text: m['text'] as String?,
          percent: m['percent'] as int?,
        );
      case 'networkStarted':
        hooks.networkStarted();
      case 'remoteMode':
        hooks.remoteMode(data as bool);
      case 'pairingPrompt':
        final m = data as Map;
        onPairingPrompt?.call(PairingPrompt(
          pairId: m['pairId'] as String,
          peerName: m['peerName'] as String,
          platform: platformFromString(m['platform'] as String?),
          code: m['code'] as String,
        ));
      case 'pairingClosed':
        final m = data as Map;
        onPairingClosed?.call(m['pairId'] as String, m['success'] as bool, m['message'] as String?);
      case 'jobEnded':
        final j = data as Map;
        final job = _jobById[j['id']] ?? TransferJob.fromJson(j);
        job.applyJson(j);
        onJobEnded?.call(job);
    }
  }

  // --------------------------------------------------------- commandes
  Future<void> saveSettings() => _cmd('saveSettings', {'settings': settings.toJson()});

  Future<Peer> probe(String host, int port, {String? expectedFingerprint}) async {
    final r = await _cmd('probe', {'host': host, 'port': port, 'fingerprint': expectedFingerprint});
    return peerFromJson(r as Map);
  }

  Future<TrustedDevice> pair(Peer peer, Future<String?> Function(String peerName, String? error) askCode) async {
    _askCode = askCode;
    try {
      final r = await _cmd('pair', {'peer': peerJson(peer)});
      return trustedFromJson(r as Map);
    } finally {
      _askCode = null;
    }
  }

  /// Envoi : direct si l'appareil est joignable, sinon via le canal inverse.
  /// Avec [share], dépôt dans un dossier partagé de l'autre appareil.
  Future<void> send(String deviceId, List<FileSource> sources, {String? share, String path = ''}) async {
    await _cmd('send', {
      'deviceId': deviceId,
      'smart': true,
      'share': share,
      'path': path,
      'sources': [
        for (final s in sources)
          {
            if (s is ContentFileSource) 'uri': s.uri,
            if (s is LocalFileSource) 'path': s.path,
            'relPath': s.relPath,
            'size': s.size,
            'modified': s.modified.millisecondsSinceEpoch,
          },
      ],
    });
  }

  Future<List<RemoteRoot>> remoteRoots(String deviceId) async {
    final r = await _cmd('roots', {'deviceId': deviceId});
    return [for (final x in (r as List)) RemoteRoot.fromJson(x as Map)];
  }

  Future<List<RemoteEntry>> remoteList(String deviceId, String share, String path) async {
    final r = await _cmd('list', {'deviceId': deviceId, 'share': share, 'path': path});
    return [for (final x in (r as List)) RemoteEntry.fromJson(x as Map)];
  }

  Future<void> download(String deviceId, String share, List<String> paths) =>
      _cmd('download', {'deviceId': deviceId, 'share': share, 'paths': paths});

  Future<void> refreshRemote() => _cmd('refreshRemote', null);
  Future<void> resolveAll() => _cmd('resolveAll', null);

  void clearFinishedJobs() {
    jobs.removeWhere((j) => !j.isActive);
    _emit();
    _cmd('clearFinished', null);
  }

  Future<void> removeTrusted(String id) => _cmd('removeTrusted', {'id': id});
  void cancelLocalPairing() => _cmd('cancelLocalPairing', null);
  void approvePairing(String pairId) => _cmd('approvePairing', {'pairId': pairId});
  Future<void> refreshDiscovery() => _cmd('discovery', {'action': 'refresh'});
  Future<void> restartDiscovery() => _cmd('discovery', {'action': 'restart'});
  Future<void> stop() => _cmd('stop', null).timeout(const Duration(seconds: 3), onTimeout: () => null);

  Future<void> dispose() async {
    await stop();
    _fromWorker.close();
    await _changes.close();
  }
}
