// Intégration Windows : zone de notification, lancement au démarrage,
// menu clic droit de l'explorateur, instance unique, espace disque.
import 'dart:async';
import 'dart:convert';
import 'dart:ffi';
import 'dart:io';

import 'package:ffi/ffi.dart';
import 'package:launch_at_startup/launch_at_startup.dart';
import 'package:path/path.dart' as p;
import 'package:tray_manager/tray_manager.dart';
import 'package:win32/win32.dart' as win;
import 'package:window_manager/window_manager.dart';

import 'platform_hooks.dart';

class WindowsHooks extends PlatformHooks {
  @override
  Future<int?> freeSpace(String dir) async => windowsFreeSpace(dir);
}

int? windowsFreeSpace(String dir) {
  if (!Platform.isWindows) return null;
  final path = dir.toNativeUtf16();
  final free = calloc<Uint64>();
  try {
    final ok = win.GetDiskFreeSpaceEx(path, free, nullptr, nullptr);
    return ok != 0 ? free.value : null;
  } catch (_) {
    return null;
  } finally {
    calloc.free(path);
    calloc.free(free);
  }
}

// ------------------------------------------------------------ instance unique
/// Une seule instance de Transferys : les lancements suivants (clic droit
/// « Envoyer avec Transferys », raccourci « Envoyer vers ») transmettent
/// leurs fichiers à la première instance puis se ferment.
class SingleInstance {
  SingleInstance(this.dataDir);
  final String dataDir;
  ServerSocket? _server;
  final _pending = <String>[];
  Timer? _batch;
  void Function(List<String> paths)? onPaths;
  void Function()? onShow;

  File get _portFile => File(p.join(dataDir, 'instance.port'));

  /// Renvoie false si une autre instance tourne déjà (les arguments lui ont été transmis).
  Future<bool> claim(List<String> args) async {
    try {
      if (await _portFile.exists()) {
        final port = int.tryParse((await _portFile.readAsString()).trim());
        if (port != null) {
          final s = await Socket.connect(InternetAddress.loopbackIPv4, port, timeout: const Duration(milliseconds: 700));
          s.write(jsonEncode({'args': args}));
          await s.flush();
          await s.close();
          return false;
        }
      }
    } catch (_) {
      // pas d'instance active : on devient l'instance principale
    }
    _server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    await Directory(dataDir).create(recursive: true);
    await _portFile.writeAsString('${_server!.port}');
    _server!.listen((sock) async {
      try {
        final txt = await utf8.decodeStream(sock);
        final j = jsonDecode(txt) as Map;
        final a = (j['args'] as List).cast<String>();
        handleArgs(a, fromOtherInstance: true);
      } catch (_) {}
    });
    return true;
  }

  /// Gère « --send <fichiers…> ». Les envois arrivant en rafale (sélection
  /// multiple dans l'explorateur) sont regroupés.
  void handleArgs(List<String> args, {bool fromOtherInstance = false}) {
    final paths = sendPathsFromArgs(args);
    if (paths.isEmpty) {
      if (fromOtherInstance) onShow?.call();
      return;
    }
    _pending.addAll(paths);
    _batch?.cancel();
    _batch = Timer(const Duration(milliseconds: 700), () {
      final list = List<String>.from(_pending);
      _pending.clear();
      onPaths?.call(list);
    });
  }

  Future<void> release() async {
    await _server?.close();
    try {
      await _portFile.delete();
    } catch (_) {}
  }
}

List<String> sendPathsFromArgs(List<String> args) {
  final i = args.indexOf('--send');
  final list = i >= 0 ? args.sublist(i + 1) : args.where((a) => !a.startsWith('--')).toList();
  return list.where((a) => a.isNotEmpty && FileSystemEntity.typeSync(a) != FileSystemEntityType.notFound).toList();
}

// ------------------------------------------------------- menu clic droit
class ExplorerMenu {
  static const _keys = [r'HKCU\Software\Classes\*\shell\Transferys', r'HKCU\Software\Classes\Directory\shell\Transferys'];

  static Future<void> install() async {
    final exe = Platform.resolvedExecutable;
    for (final k in _keys) {
      await Process.run('reg', ['add', k, '/v', 'MUIVerb', '/d', 'Envoyer avec Transferys', '/f']);
      await Process.run('reg', ['add', k, '/v', 'Icon', '/d', '"$exe",0', '/f']);
      // Sélection multiple : une seule fenêtre grâce à l'instance unique.
      await Process.run('reg', ['add', k, '/v', 'MultiSelectModel', '/d', 'Player', '/f']);
      await Process.run('reg', ['add', '$k\\command', '/ve', '/d', '"$exe" --send "%1"', '/f']);
    }
  }

  static Future<void> uninstall() async {
    for (final k in _keys) {
      await Process.run('reg', ['delete', k, '/f']);
    }
  }
}

// ------------------------------------------------------ démarrage auto
class AutoStart {
  static void setup() {
    launchAtStartup.setup(appName: 'Transferys', appPath: '"${Platform.resolvedExecutable}"', args: ['--minimized']);
  }

  static Future<void> set(bool enabled) async {
    setup();
    if (enabled) {
      await launchAtStartup.enable();
    } else {
      await launchAtStartup.disable();
    }
  }
}

// ------------------------------------------------------- zone de notification
class TrayController with TrayListener, WindowListener {
  TrayController({required this.onOpen, required this.onSend, required this.onQuit, required this.minimizeToTray});
  final void Function() onOpen;
  final void Function() onSend;
  final Future<void> Function() onQuit;
  final bool Function() minimizeToTray;

  Future<void> init() async {
    trayManager.addListener(this);
    windowManager.addListener(this);
    await windowManager.setPreventClose(true);
    final ico = p.join(p.dirname(Platform.resolvedExecutable), 'data', 'flutter_assets', 'assets', 'tray.ico');
    await trayManager.setIcon(File(ico).existsSync() ? ico : 'assets/tray.ico');
    await trayManager.setToolTip('Transferys : prêt à recevoir');
    await trayManager.setContextMenu(Menu(items: [
      MenuItem(key: 'open', label: 'Ouvrir Transferys'),
      MenuItem(key: 'send', label: 'Envoyer des fichiers…'),
      MenuItem.separator(),
      MenuItem(key: 'quit', label: 'Quitter Transferys'),
    ]));
  }

  Future<void> setTooltip(String t) => trayManager.setToolTip(t);

  @override
  void onTrayIconMouseDown() => onOpen();

  @override
  void onTrayIconRightMouseDown() => trayManager.popUpContextMenu();

  @override
  void onTrayMenuItemClick(MenuItem item) {
    switch (item.key) {
      case 'open':
        onOpen();
        break;
      case 'send':
        onSend();
        break;
      case 'quit':
        onQuit();
        break;
    }
  }

  @override
  void onWindowClose() async {
    if (minimizeToTray()) {
      await windowManager.hide();
    } else {
      await onQuit();
    }
  }
}

Future<void> showMainWindow() async {
  await windowManager.show();
  if (await windowManager.isMinimized()) await windowManager.restore();
  await windowManager.focus();
}
