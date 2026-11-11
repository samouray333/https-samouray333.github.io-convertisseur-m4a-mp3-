// Fonctions système communes : notifications, ouverture de fichiers et
// dossiers, dossier de réception par défaut, nom d'appareil par défaut.
import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';

import 'android_bridge.dart';

class Notifier {
  static final _plugin = FlutterLocalNotificationsPlugin();
  static bool _ready = false;
  static int _id = 100;
  static void Function(String? payload)? onTap;

  static Future<void> init() async {
    try {
      await _plugin.initialize(
        settings: const InitializationSettings(
          android: AndroidInitializationSettings('@drawable/ic_stat_transferys'),
          linux: LinuxInitializationSettings(defaultActionName: 'Ouvrir'),
          windows: WindowsInitializationSettings(
            appName: 'Transferys',
            appUserModelId: 'QMTech.Transferys.App.1',
            guid: '8f3c2a1e-5b7d-4e9a-9c41-2d6f0b7a3e15',
          ),
        ),
        onDidReceiveNotificationResponse: (r) => onTap?.call(r.payload),
      );
      _ready = true;
    } catch (_) {
      _ready = false;
    }
  }

  static Future<void> show(String title, String body, {String? payload, bool important = false}) async {
    if (!_ready) return;
    try {
      await _plugin.show(
        id: _id++,
        title: title,
        body: body,
        payload: payload,
        notificationDetails: NotificationDetails(
          android: AndroidNotificationDetails(
            important ? 'transferys_requests' : 'transferys_done',
            important ? 'Demandes de réception' : 'Transferts terminés',
            channelDescription: important ? 'Un appareil veut vous envoyer des fichiers' : 'Fin des réceptions et des envois',
            importance: important ? Importance.max : Importance.defaultImportance,
            priority: important ? Priority.high : Priority.defaultPriority,
            icon: '@drawable/ic_stat_transferys',
          ),
        ),
      );
    } catch (_) {}
  }
}

Future<String> defaultReceiveDir() async {
  if (Platform.isAndroid) return p.join(await AndroidBridge.downloadsDir(), 'Transferys');
  Directory? d;
  try {
    d = await getDownloadsDirectory();
  } catch (_) {}
  final base = d?.path ??
      p.join(Platform.environment['USERPROFILE'] ?? Platform.environment['HOME'] ?? '.', 'Downloads');
  return p.join(base, 'Transferys');
}

Future<String> defaultDeviceName() async {
  if (Platform.isAndroid) {
    final m = await AndroidBridge.deviceModel();
    return 'Tel $m';
  }
  final user = Platform.environment['USERNAME'] ?? Platform.environment['USER'];
  if (user != null && user.isNotEmpty) return 'PC de $user';
  return 'PC ${Platform.localHostname}';
}

Future<bool> openFilePath(String path) async {
  if (Platform.isAndroid) return AndroidBridge.openFile(path);
  if (Platform.isWindows) {
    try {
      await Process.start('explorer', [path], mode: ProcessStartMode.detached);
      return true;
    } catch (_) {}
  }
  return launchUrl(Uri.file(path));
}

/// Ouvre le dossier ; sous Windows, sélectionne le fichier si [selectFile].
Future<bool> openFolderPath(String folder, {String? selectFile}) async {
  if (Platform.isAndroid) return AndroidBridge.openFolder(folder);
  if (Platform.isWindows) {
    try {
      if (selectFile != null && File(selectFile).existsSync()) {
        await Process.start('explorer', ['/select,', selectFile], mode: ProcessStartMode.detached);
      } else {
        await Process.start('explorer', [folder], mode: ProcessStartMode.detached);
      }
      return true;
    } catch (_) {}
  }
  return launchUrl(Uri.directory(folder));
}
