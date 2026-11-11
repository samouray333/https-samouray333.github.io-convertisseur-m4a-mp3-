// État global de l'interface : relie le moteur aux écrans et aux dialogues.
import 'dart:async';
import 'dart:io';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import '../core/errors.dart';
import '../core/format.dart';
import '../core/models.dart';
import '../core/settings.dart';
import '../network/net_utils.dart';
import '../platform/android_bridge.dart';
import '../platform/platform_hooks.dart';
import '../platform/system.dart';
import '../platform/windows_integration.dart';
import '../transfer/file_source.dart';
import '../transfer/job.dart';
import '../transfer/receiver.dart';
import '../transfer/server.dart';
import '../worker/engine_proxy.dart';
import 'dialogs.dart';

/// Un appareil affiché dans la liste (visible et/ou de confiance).
class DeviceEntry {
  DeviceEntry(this.peer, this.trusted, {this.remote = false});

  /// Joignable via Internet (accès à distance) alors qu'il n'est pas sur ce réseau.
  final bool remote;
  final Peer? peer;
  final TrustedDevice? trusted;
  String get id => peer?.id ?? trusted!.id;
  String get name => trusted?.name ?? peer!.name;
  DevicePlatform get platform => trusted?.platform ?? peer!.platform;
  bool get online => peer != null || remote;
  bool get isTrusted => trusted != null;
}

class AppState extends ChangeNotifier {
  AppState({this.dataDirOverride});
  final String? dataDirOverride;

  late EngineProxy engine;
  final navKey = GlobalKey<NavigatorState>();
  final messengerKey = GlobalKey<ScaffoldMessengerState>();

  bool ready = false;
  String? networkError;
  List<LocalAddress> localAddresses = [];
  final selection = <FileSource>[];
  int tab = 0;
  bool scanning = false;
  Timer? _addrTimer;
  Timer? _throttle;
  SingleInstance? singleInstance;
  TrayController? tray;

  bool get isAndroid => Platform.isAndroid;
  bool get isWindows => Platform.isWindows;
  bool get isDesktop => Platform.isWindows || Platform.isLinux || Platform.isMacOS;
  Settings get settings => engine.settings;

  ThemeMode get themeMode => switch (settings.themeMode) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };

  Future<void> init() async {
    final dataDir = dataDirOverride ?? (await getApplicationSupportDirectory()).path;
    final defaults = Settings(deviceName: await defaultDeviceName(), receiveDir: await defaultReceiveDir());
    final PlatformHooks hooks = isAndroid ? AndroidHooks() : (isWindows ? WindowsHooks() : DefaultPlatformHooks());
    engine = EngineProxy(
      platform: isAndroid
          ? DevicePlatform.android
          : isWindows
              ? DevicePlatform.windows
              : DevicePlatform.linux,
      hooks: hooks,
    );
    engine.onIncoming = _onIncoming;
    engine.onPairingPrompt = _onPairingPrompt;
    engine.onPairingClosed = _onPairingClosed;
    engine.onJobEnded = _onJobEnded;
    engine.changes.listen((_) => _scheduleNotify());
    // Le moteur réseau tourne dans son propre isolate (débit maximal).
    await engine.start(dataDir: dataDir, defaults: defaults);
    networkError = engine.startError;
    await _refreshAddresses();
    _addrTimer = Timer.periodic(const Duration(seconds: 10), (_) => _refreshAddresses());
    // Vérifie régulièrement quels appareils de confiance sont joignables (y compris à distance).
    Timer.periodic(const Duration(seconds: 60), (_) => engine.resolveAll().catchError((_) {}));
    unawaited(engine.resolveAll().catchError((_) {}));
    if (isAndroid) {
      AndroidBridge.init();
      AndroidBridge.onShared = (items) {
        addSources(items);
        tab = 0;
        notifyListeners();
      };
      try {
        addSources(await AndroidBridge.initialShare());
      } catch (_) {}
    }
    Notifier.onTap = (payload) {
      if (isWindows) showMainWindow();
      if (payload != null && payload.startsWith('folder:')) {
        openFolderPath(payload.substring(7));
      }
    };
    ready = true;
    notifyListeners();
  }

  Future<void> _refreshAddresses() async {
    final before = localAddresses.map((e) => e.address.address).join(',');
    localAddresses = await localIPv4Addresses();
    final after = localAddresses.map((e) => e.address.address).join(',');
    if (before != after) {
      // Changement de réseau : on relance la découverte.
      if (before.isNotEmpty) await engine.restartDiscovery();
      notifyListeners();
    }
  }

  void _scheduleNotify() {
    if (_throttle != null) return;
    _throttle = Timer(const Duration(milliseconds: 150), () {
      _throttle = null;
      notifyListeners();
      _updateTray();
    });
  }

  void _updateTray() {
    final t = tray;
    if (t == null) return;
    final active = activeJobs;
    if (active.isEmpty) {
      t.setTooltip('Transferys : prêt à recevoir');
    } else {
      t.setTooltip('Transferys : ${active.length} transfert(s), ${(active.first.progress * 100).toStringAsFixed(0)} %');
    }
  }

  @override
  void dispose() {
    _addrTimer?.cancel();
    engine.dispose();
    super.dispose();
  }

  // ------------------------------------------------------------- appareils
  List<DeviceEntry> get devices {
    final list = engine
        .devices()
        .map((e) => DeviceEntry(e.$1, e.$2, remote: e.$1 == null && e.$2 != null && engine.reachable.contains(e.$2!.id)))
        .toList();
    list.sort((a, b) {
      if (a.online != b.online) return a.online ? -1 : 1;
      if (a.isTrusted != b.isTrusted) return a.isTrusted ? -1 : 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });
    return list;
  }

  Future<void> refreshDevices() async {
    scanning = true;
    notifyListeners();
    await _refreshAddresses();
    await engine.refreshDiscovery();
    await engine.resolveAll().catchError((_) {});
    networkError = engine.discoveryError ?? engine.startError;
    await Future.delayed(const Duration(milliseconds: 1500));
    scanning = false;
    notifyListeners();
  }

  List<TransferJob> get activeJobs => engine.jobs.where((j) => j.isActive).toList();

  // ------------------------------------------------------------- sélection
  void addSources(List<FileSource> items) {
    final known = selection.map((s) => s.relPath).toSet();
    for (final s in items) {
      if (!known.contains(s.relPath) || s is! LocalFileSource) selection.add(s);
    }
    notifyListeners();
  }

  Future<void> addPaths(List<String> paths) async => addSources(await expandLocalPaths(paths));

  void removeSourceAt(int i) {
    selection.removeAt(i);
    notifyListeners();
  }

  void clearSelection() {
    selection.clear();
    notifyListeners();
  }

  int get selectionSize => selection.fold(0, (a, s) => a + s.size);

  Future<void> pickFiles() async {
    try {
      if (isAndroid) {
        addSources(await AndroidBridge.pickFiles());
      } else {
        final files = await openFiles();
        await addPaths(files.map((f) => f.path).toList());
      }
    } catch (e) {
      toast('Impossible d\'ouvrir le sélecteur de fichiers : $e');
    }
  }

  Future<void> pickFolder() async {
    try {
      if (isAndroid) {
        final items = await AndroidBridge.pickFolder();
        if (items.isEmpty) return;
        addSources(items);
      } else {
        final dir = await getDirectoryPath(confirmButtonText: 'Choisir ce dossier');
        if (dir != null) await addPaths([dir]);
      }
    } catch (e) {
      toast('Impossible de lire ce dossier : $e');
    }
  }

  Future<void> pickMedia() async {
    try {
      addSources(await AndroidBridge.pickMedia());
    } catch (e) {
      toast('Impossible d\'ouvrir la galerie : $e');
    }
  }

  // ------------------------------------------------------------------ envoi
  /// Envoie la sélection à [d] (appairage d'abord si nécessaire).
  Future<void> sendTo(DeviceEntry d) async {
    var trusted = d.trusted;
    if (selection.isEmpty) {
      if (trusted == null && d.peer != null) {
        await pairWith(d.peer!);
      } else {
        toast('Choisissez d\'abord des fichiers à envoyer.');
      }
      return;
    }
    if (trusted == null) {
      if (d.peer == null) return;
      trusted = await pairWith(d.peer!);
      if (trusted == null) return;
    }
    try {
      await engine.send(trusted.id, List.of(selection));
      selection.clear();
      tab = 1;
      notifyListeners();
    } on TransferysException catch (e) {
      toast(e.message);
    }
  }

  /// Appairage avec saisie du code affiché sur l'autre appareil.
  Future<TrustedDevice?> pairWith(Peer peer) async {
    final ctx = navKey.currentContext;
    if (ctx == null) return null;
    final controller = CodeEntryController();
    showCodeEntryDialog(ctx, peer.name, controller);
    try {
      final dev = await engine.pair(peer, (name, err) => controller.ask(name, err));
      controller.close();
      toast('${dev.name} est maintenant un appareil de confiance.');
      notifyListeners();
      return dev;
    } on TransferysException catch (e) {
      controller.close();
      if (e.message != 'Appairage annulé.') showErrorDialog('Appairage impossible', e.message);
      return null;
    } catch (e) {
      controller.close();
      showErrorDialog('Appairage impossible', '$e');
      return null;
    }
  }

  /// Ajoute un appareil par IP (ou depuis un QR code), puis propose l'appairage.
  Future<Peer?> connectManual(String host, int port, {String? fingerprint}) async {
    try {
      return await engine.probe(host.trim(), port, expectedFingerprint: fingerprint);
    } on TransferysException catch (e) {
      showErrorDialog('Connexion impossible', e.message);
      return null;
    }
  }

  // -------------------------------------------------------------- réception
  Future<bool> _onIncoming(IncomingRequest r) async {
    if (isWindows) await showMainWindow();
    final n = r.files.length;
    Notifier.show('Demande de réception', '${r.from.name} veut vous envoyer $n fichier(s) (${formatSize(r.totalSize)}).',
        important: true);
    final ctx = navKey.currentContext;
    if (ctx == null) return false;
    final ok = await showIncomingDialog(ctx, r);
    if (ok) tab = 1;
    notifyListeners();
    return ok;
  }

  final _pairingDialogs = <String, PairingCodeController>{};

  void _onPairingPrompt(PairingPrompt p) {
    if (isWindows) showMainWindow();
    final ctx = navKey.currentContext;
    if (ctx == null) return;
    Notifier.show('Appairage', '${p.peerName} veut s\'appairer : code ${p.code}', important: true);
    final c = PairingCodeController();
    _pairingDialogs[p.pairId] = c;
    showPairingCodeDialog(ctx, p, c, () => engine.approvePairing(p.pairId)).then((cancelled) {
      _pairingDialogs.remove(p.pairId);
      if (cancelled == true) engine.cancelLocalPairing();
    });
  }

  void _onPairingClosed(String pairId, bool success, String? message) {
    _pairingDialogs.remove(pairId)?.close();
    if (message != null) toast(message);
    notifyListeners();
  }

  void _onJobEnded(TransferJob job) {
    final ok = job.status == TransferStatus.done;
    if (job.direction == TransferDirection.receive) {
      if (ok) {
        Notifier.show('Fichiers reçus',
            '${job.doneCount} fichier(s) reçu(s) de ${job.peerName} (${formatSize(job.totalSize)}).',
            payload: job.folder != null ? 'folder:${job.folder}' : null);
      } else if (job.status != TransferStatus.cancelled) {
        Notifier.show('Réception interrompue', job.error ?? 'La réception depuis ${job.peerName} a échoué.');
      }
    } else {
      if (ok) {
        toast('Envoi terminé vers ${job.peerName}.');
        if (isAndroid) Notifier.show('Envoi terminé', '${job.files.length} fichier(s) envoyé(s) à ${job.peerName}.');
      } else if (job.status == TransferStatus.failed || job.status == TransferStatus.rejected) {
        Notifier.show('Envoi interrompu', job.error ?? 'L\'envoi vers ${job.peerName} a échoué.');
      }
    }
  }

  // ------------------------------------------------- dossiers partagés
  Future<void> addShare() async {
    final dir = await chooseFolder();
    if (dir == null) return;
    if (settings.shares.any((s) => s.path == dir)) {
      toast('Ce dossier est déjà partagé.');
      return;
    }
    final name = dir.split(RegExp(r'[\\/]')).where((e) => e.isNotEmpty).lastOrNull ?? dir;
    await updateSettings((s) => s.shares = [...s.shares, SharedFolder(path: dir, name: name)]);
  }

  Future<void> removeShare(SharedFolder f) =>
      updateSettings((s) => s.shares = s.shares.where((x) => x.path != f.path).toList());

  Future<void> setShareWritable(SharedFolder f, bool v) => updateSettings((s) {
        s.shares = [
          for (final x in s.shares) x.path == f.path ? SharedFolder(path: x.path, name: x.name, writable: v) : x,
        ];
      });

  /// Choix d'un dossier (Android : accès à tous les fichiers si nécessaire).
  Future<String?> chooseFolder() async {
    if (isAndroid) {
      final dir = await AndroidBridge.pickDirectory();
      if (dir == null) return null;
      if (!await AndroidBridge.hasAllFilesAccess()) {
        toast('Pour partager ce dossier, autorisez « Accès à tous les fichiers » pour Transferys.');
        await AndroidBridge.requestAllFilesAccess();
        await Future.delayed(const Duration(seconds: 1));
        if (!await AndroidBridge.hasAllFilesAccess()) return null;
      }
      return dir;
    }
    return getDirectoryPath(confirmButtonText: 'Partager ce dossier');
  }

  Future<void> setRemoteAccess(bool v) async {
    await updateSettings((s) => s.remoteAccess = v);
    if (v && isAndroid && !await AndroidBridge.ignoringBatteryOptimizations()) {
      toast('Conseillé : autorisez Transferys à ignorer l\'optimisation de batterie, sinon Android coupera l\'accès à distance.');
      await AndroidBridge.requestIgnoreBatteryOptimizations();
    }
  }

  // --------------------------------------------------------------- réglages
  Future<void> updateSettings(void Function(Settings s) change) async {
    change(settings);
    await engine.saveSettings();
    notifyListeners();
  }

  Future<String?> chooseReceiveDir() async {
    if (isAndroid) {
      // Android : hors Téléchargements / Documents, l'accès à tous les
      // fichiers est nécessaire pour y écrire directement.
      final dir = await AndroidBridge.pickDirectory();
      if (dir == null) return null;
      final lower = dir.toLowerCase();
      final shared = lower.contains('/download') || lower.contains('/documents');
      if (!shared && !await AndroidBridge.hasAllFilesAccess()) {
        toast('Pour recevoir dans ce dossier, autorisez « Accès à tous les fichiers » pour Transferys.');
        await AndroidBridge.requestAllFilesAccess();
        if (!await AndroidBridge.hasAllFilesAccess()) return null;
      }
      return dir;
    }
    return getDirectoryPath(initialDirectory: settings.receiveDir, confirmButtonText: 'Recevoir ici');
  }

  // ------------------------------------------------------------- messages
  void toast(String msg) {
    messengerKey.currentState
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(msg), behavior: SnackBarBehavior.floating, duration: const Duration(seconds: 5)));
  }

  void showErrorDialog(String title, String message) {
    final ctx = navKey.currentContext;
    if (ctx == null) return;
    showDialog<void>(
      context: ctx,
      builder: (c) => AlertDialog(
        icon: const Icon(Icons.error_outline),
        title: Text(title),
        content: Text(message),
        actions: [TextButton(onPressed: () => Navigator.pop(c), child: const Text('OK'))],
      ),
    );
  }

  void setTab(int i) {
    tab = i;
    notifyListeners();
  }
}
