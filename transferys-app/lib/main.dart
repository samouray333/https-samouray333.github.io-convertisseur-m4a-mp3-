// Point d'entrée de Transferys (Android et Windows).
import 'dart:async';
import 'dart:io';


import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:window_manager/window_manager.dart';

import 'platform/system.dart';
import 'platform/windows_integration.dart';
import 'ui/app_state.dart';
import 'ui/brand.dart';
import 'ui/home_shell.dart';
import 'ui/screens/onboarding_screen.dart';

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final startMinimized = args.contains('--minimized');
  SingleInstance? single;

  if (Platform.isWindows) {
    final dataDir = (await getApplicationSupportDirectory()).path;
    single = SingleInstance(dataDir);
    if (!await single.claim(args)) {
      // Une instance tourne déjà : elle a reçu nos fichiers.
      exit(0);
    }
    await windowManager.ensureInitialized();
    await windowManager.waitUntilReadyToShow(
      const WindowOptions(
        title: 'Transferys',
        size: Size(1080, 760),
        minimumSize: Size(440, 600),
        center: true,
      ),
      () async {
        if (!startMinimized) {
          await windowManager.show();
          await windowManager.focus();
        }
      },
    );
  }

  await Notifier.init();
  final app = AppState();
  await app.init();

  if (Platform.isWindows) {
    app.singleInstance = single;
    Future<void> quit() async {
      await app.engine.stop();
      await single?.release();
      await windowManager.setPreventClose(false);
      await windowManager.destroy();
      exit(0);
    }

    final tray = TrayController(
      onOpen: showMainWindow,
      onSend: () async {
        await showMainWindow();
        app.setTab(0);
        await app.pickFiles();
      },
      onQuit: quit,
      minimizeToTray: () => app.settings.minimizeToTray,
    );
    try {
      await tray.init();
      app.tray = tray;
    } catch (_) {}
    single!
      ..onPaths = (paths) async {
        await showMainWindow();
        await app.addPaths(paths);
        app.setTab(0);
      }
      ..onShow = showMainWindow
      ..handleArgs(args);
    // Garde le menu clic droit et le démarrage auto alignés sur l'exe actuel.
    unawaited(() async {
      try {
        if (app.settings.explorerMenu) await ExplorerMenu.install();
        await AutoStart.set(app.settings.autoStart);
      } catch (_) {}
    }());
  }

  if (!Platform.isWindows && args.contains('--send')) {
    // Linux / tests : fichiers passés en ligne de commande.
    await app.addPaths(sendPathsFromArgs(args));
  }

  runApp(ChangeNotifierProvider.value(value: app, child: const TransferysApp()));
}

class TransferysApp extends StatelessWidget {
  const TransferysApp({super.key});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    return MaterialApp(
      title: 'Transferys',
      debugShowCheckedModeBanner: false,
      navigatorKey: app.navKey,
      scaffoldMessengerKey: app.messengerKey,
      theme: buildTheme(Brightness.light),
      darkTheme: buildTheme(Brightness.dark),
      themeMode: app.themeMode,
      locale: const Locale('fr', 'FR'),
      supportedLocales: const [Locale('fr', 'FR')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: app.settings.onboardingDone ? const HomeShell() : const OnboardingScreen(),
    );
  }
}
