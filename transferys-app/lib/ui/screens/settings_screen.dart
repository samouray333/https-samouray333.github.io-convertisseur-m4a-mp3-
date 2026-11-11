// Écran « Réglages ».
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/models.dart';
import '../../engine.dart';
import '../../platform/android_bridge.dart';
import '../../platform/windows_integration.dart';
import '../app_state.dart';
import '../widgets.dart';
import 'help_screen.dart';
import 'onboarding_screen.dart';
import 'trusted_devices_screen.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final s = app.settings;
    return ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 32), children: [
      const SectionTitle('Cet appareil'),
      Card(
        child: Column(children: [
          ListTile(
            leading: const Icon(Icons.badge_outlined),
            title: const Text('Nom de l\'appareil'),
            subtitle: Text(s.deviceName),
            trailing: const Icon(Icons.edit_outlined),
            onTap: () => _editName(context, app),
          ),
          ListTile(
            leading: const Icon(Icons.folder_outlined),
            title: const Text('Dossier de réception'),
            subtitle: Text(s.receiveDir),
            trailing: const Icon(Icons.edit_outlined),
            onTap: () async {
              final dir = await app.chooseReceiveDir();
              if (dir != null) await app.updateSettings((x) => x.receiveDir = dir);
            },
          ),
        ]),
      ),
      const SectionTitle('Réception'),
      Card(
        child: Column(children: [
          SwitchListTile(
            secondary: const Icon(Icons.verified_user_outlined),
            title: const Text('Demander confirmation avant chaque réception'),
            subtitle: const Text('Recommandé. Sinon, les appareils de confiance envoient directement.'),
            value: s.confirmBeforeReceive,
            onChanged: (v) => app.updateSettings((x) => x.confirmBeforeReceive = v),
          ),
          ListTile(
            leading: const Icon(Icons.file_copy_outlined),
            title: const Text('Si un fichier existe déjà'),
            subtitle: Text(_dupLabel(s.duplicateMode)),
            trailing: DropdownButton<DuplicateMode>(
              value: s.duplicateMode,
              underline: const SizedBox(),
              items: [
                for (final m in DuplicateMode.values) DropdownMenuItem(value: m, child: Text(_dupShort(m))),
              ],
              onChanged: (m) {
                if (m != null) app.updateSettings((x) => x.duplicateMode = m);
              },
            ),
          ),
          ListTile(
            leading: const Icon(Icons.devices_outlined),
            title: const Text('Appareils de confiance'),
            subtitle: Text('${app.engine.trust.all.length} appareil(s)'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const TrustedDevicesScreen())),
          ),
        ]),
      ),
      const SectionTitle('Apparence'),
      Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'system', icon: Icon(Icons.brightness_auto_outlined), label: Text('Système')),
              ButtonSegment(value: 'light', icon: Icon(Icons.light_mode_outlined), label: Text('Clair')),
              ButtonSegment(value: 'dark', icon: Icon(Icons.dark_mode_outlined), label: Text('Sombre')),
            ],
            selected: {s.themeMode},
            onSelectionChanged: (v) => app.updateSettings((x) => x.themeMode = v.first),
          ),
        ),
      ),
      if (Platform.isWindows) ...[
        const SectionTitle('Windows'),
        Card(
          child: Column(children: [
            SwitchListTile(
              secondary: const Icon(Icons.power_settings_new_rounded),
              title: const Text('Lancer au démarrage de Windows'),
              subtitle: const Text('Transferys démarre discrètement dans la zone de notification.'),
              value: s.autoStart,
              onChanged: (v) async {
                try {
                  await AutoStart.set(v);
                  await app.updateSettings((x) => x.autoStart = v);
                } catch (e) {
                  app.toast('Impossible de modifier le démarrage automatique : $e');
                }
              },
            ),
            SwitchListTile(
              secondary: const Icon(Icons.minimize_rounded),
              title: const Text('Fermer = rester dans la zone de notification'),
              subtitle: const Text('Transferys continue de recevoir en arrière-plan.'),
              value: s.minimizeToTray,
              onChanged: (v) => app.updateSettings((x) => x.minimizeToTray = v),
            ),
            SwitchListTile(
              secondary: const Icon(Icons.ads_click_rounded),
              title: const Text('« Envoyer avec Transferys » dans le clic droit'),
              subtitle: const Text('Dans l\'explorateur, sur les fichiers et les dossiers.'),
              value: s.explorerMenu,
              onChanged: (v) async {
                try {
                  if (v) {
                    await ExplorerMenu.install();
                  } else {
                    await ExplorerMenu.uninstall();
                  }
                  await app.updateSettings((x) => x.explorerMenu = v);
                } catch (e) {
                  app.toast('Impossible de modifier le menu contextuel : $e');
                }
              },
            ),
          ]),
        ),
      ],
      if (Platform.isAndroid) ...[
        const SectionTitle('Android'),
        Card(
          child: Column(children: [
            ListTile(
              leading: const Icon(Icons.battery_saver_outlined),
              title: const Text('Ne pas limiter la batterie'),
              subtitle: const Text('Évite qu\'Android coupe Transferys pendant les longs transferts écran éteint.'),
              trailing: const Icon(Icons.chevron_right),
              onTap: AndroidBridge.requestIgnoreBatteryOptimizations,
            ),
            ListTile(
              leading: const Icon(Icons.notifications_outlined),
              title: const Text('Notifications'),
              subtitle: const Text('Pour voir la progression et les demandes de réception.'),
              trailing: const Icon(Icons.chevron_right),
              onTap: AndroidBridge.requestNotificationPermission,
            ),
          ]),
        ),
      ],
      const SectionTitle('Aide'),
      Card(
        child: Column(children: [
          ListTile(
            leading: const Icon(Icons.help_outline_rounded),
            title: const Text('Problèmes de connexion'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const HelpScreen())),
          ),
          ListTile(
            leading: const Icon(Icons.school_outlined),
            title: const Text('Revoir le guide de démarrage'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const OnboardingScreen(replay: true))),
          ),
          const ListTile(
            leading: Icon(Icons.info_outline_rounded),
            title: Text('Transferys $appVersion'),
            subtitle: Text('QMTech • Tout reste sur votre réseau local : aucun serveur, aucune donnée envoyée sur Internet.'),
          ),
        ]),
      ),
    ]);
  }

  static String _dupShort(DuplicateMode m) => switch (m) {
        DuplicateMode.rename => 'Renommer',
        DuplicateMode.replace => 'Remplacer',
        DuplicateMode.skip => 'Ignorer',
      };

  static String _dupLabel(DuplicateMode m) => switch (m) {
        DuplicateMode.rename => 'Renommer automatiquement : « photo (1).jpg »',
        DuplicateMode.replace => 'Remplacer l\'ancien fichier',
        DuplicateMode.skip => 'Ne pas recevoir le fichier',
      };

  Future<void> _editName(BuildContext context, AppState app) async {
    final c = TextEditingController(text: app.settings.deviceName);
    final v = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Nom de l\'appareil'),
        content: TextField(
          controller: c,
          autofocus: true,
          maxLength: 40,
          decoration: const InputDecoration(hintText: 'ex. PC Bureau, Tel Quentin'),
          onSubmitted: (x) => Navigator.pop(ctx, x),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Annuler')),
          FilledButton(onPressed: () => Navigator.pop(ctx, c.text), child: const Text('Enregistrer')),
        ],
      ),
    );
    if (v != null && v.trim().isNotEmpty) await app.updateSettings((x) => x.deviceName = v.trim());
  }
}
