// Pont vers le code natif Android (Kotlin, MainActivity.kt) : sélecteurs de
// fichiers sans copie, menu Partager, service au premier plan, espace
// disque, galerie, verrou multicast, ouverture de fichiers.
import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';

import '../transfer/file_source.dart';
import 'platform_hooks.dart';

class AndroidBridge {
  static const _ch = MethodChannel('fr.qmtech.transferys/native');
  static void Function(List<FileSource> items)? onShared;

  static void init() {
    _ch.setMethodCallHandler((call) async {
      if (call.method == 'onShare') {
        final items = _parse(call.arguments);
        if (items.isNotEmpty) onShared?.call(items);
      }
      return null;
    });
  }

  static List<FileSource> _parse(dynamic raw) {
    if (raw is! List) return const [];
    return raw
        .whereType<Map>()
        .map((m) => ContentFileSource(
              uri: m['uri'] as String,
              relPath: (m['relPath'] as String?) ?? (m['name'] as String? ?? 'fichier'),
              size: (m['size'] as num?)?.toInt() ?? 0,
              modified: DateTime.fromMillisecondsSinceEpoch((m['modified'] as num?)?.toInt() ?? DateTime.now().millisecondsSinceEpoch),
            ))
        .toList();
  }

  static Future<List<FileSource>> pickFiles() async => _parse(await _ch.invokeMethod('pickFiles'));
  static Future<List<FileSource>> pickMedia() async => _parse(await _ch.invokeMethod('pickMedia'));
  static Future<List<FileSource>> pickFolder() async => _parse(await _ch.invokeMethod('pickFolder'));

  /// Choix d'un dossier (chemin réel, ex. /storage/emulated/0/Download/X).
  static Future<String?> pickDirectory() => _ch.invokeMethod<String>('pickDirectory');

  /// Fichiers reçus via « Partager » au lancement de l'appli.
  static Future<List<FileSource>> initialShare() async => _parse(await _ch.invokeMethod('initialShare'));

  static Future<String> deviceModel() async => (await _ch.invokeMethod<String>('deviceModel')) ?? 'Android';
  static Future<int> sdkInt() async => (await _ch.invokeMethod<int>('sdkInt')) ?? 33;
  static Future<String> downloadsDir() async =>
      (await _ch.invokeMethod<String>('downloadsDir')) ?? '/storage/emulated/0/Download';

  static Future<int?> freeSpace(String path) => _ch.invokeMethod<int>('freeSpace', {'path': path});
  static Future<void> scanFile(String path) => _ch.invokeMethod('scanFile', {'path': path});
  static Future<bool> openFile(String path) async => (await _ch.invokeMethod<bool>('openFile', {'path': path})) ?? false;
  static Future<bool> openFolder(String path) async => (await _ch.invokeMethod<bool>('openFolder', {'path': path})) ?? false;
  static Future<bool> shareFile(String path) async => (await _ch.invokeMethod<bool>('shareFile', {'path': path})) ?? false;
  /// Descripteur de fichier d'un content:// (valable dans tout le processus).
  static Future<int?> openFdRaw(String uri) => _ch.invokeMethod<int>('openFd', {'uri': uri});
  static Future<void> closeFdRaw(int fd) => _ch.invokeMethod('closeFd', {'fd': fd});

  static Future<void> acquireNetworkLocks() => _ch.invokeMethod('acquireLocks');

  static Future<void> serviceUpdate({required bool active, String? title, String? text, int? percent}) =>
      _ch.invokeMethod('service', {'active': active, 'title': title, 'text': text, 'percent': percent});

  /// Android 8-9 : permission d'écriture classique.
  static Future<bool> requestLegacyStorage() async => (await _ch.invokeMethod<bool>('requestLegacyStorage')) ?? true;

  /// Accès à tous les fichiers (uniquement si dossier personnalisé hors Téléchargements).
  static Future<bool> hasAllFilesAccess() async => (await _ch.invokeMethod<bool>('hasAllFilesAccess')) ?? false;
  static Future<void> requestAllFilesAccess() => _ch.invokeMethod('requestAllFilesAccess');
  static Future<bool> requestNotificationPermission() async =>
      (await _ch.invokeMethod<bool>('requestNotifications')) ?? true;
  static Future<bool> ignoringBatteryOptimizations() async =>
      (await _ch.invokeMethod<bool>('ignoringBattery')) ?? true;
  static Future<void> requestIgnoreBatteryOptimizations() => _ch.invokeMethod('requestIgnoreBattery');
}

/// Contenu Android (content://) lu directement via son descripteur de
/// fichier : aucune copie, même pour une vidéo de plusieurs Go.
class ContentFileSource extends FileSource {
  ContentFileSource({required this.uri, required this.relPath, required this.size, required this.modified});
  final String uri;
  @override
  final String relPath;
  @override
  final int size;
  @override
  final DateTime modified;

  @override
  Future<RandomAccessFile> open() async {
    final fd = await AndroidBridge._ch.invokeMethod<int>('openFd', {'uri': uri});
    if (fd == null || fd < 0) throw const FileSystemException('Fichier illisible');
    try {
      return await File('/proc/self/fd/$fd').open(mode: FileMode.read);
    } finally {
      await AndroidBridge._ch.invokeMethod('closeFd', {'fd': fd});
    }
  }
}

class AndroidHooks extends PlatformHooks {
  @override
  Future<int?> freeSpace(String dir) => AndroidBridge.freeSpace(dir).catchError((_) => null);

  @override
  Future<void> fileSaved(String path) => AndroidBridge.scanFile(path).catchError((_) {});

  @override
  Future<void> transferActivity({required bool active, String? title, String? text, int? percent}) =>
      AndroidBridge.serviceUpdate(active: active, title: title, text: text, percent: percent).catchError((_) {});

  @override
  Future<void> networkStarted() => AndroidBridge.acquireNetworkLocks().catchError((_) {});
}
