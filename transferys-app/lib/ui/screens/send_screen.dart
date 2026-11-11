// Écran « Envoyer » : sélection des fichiers (glisser-déposer sur PC) et
// liste des appareils détectés.
import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../security/identity.dart';
import '../app_state.dart';
import '../brand.dart';
import '../widgets.dart';
import 'add_device_screen.dart';
import 'help_screen.dart';

class SendScreen extends StatefulWidget {
  const SendScreen({super.key});
  @override
  State<SendScreen> createState() => _SendScreenState();
}

class _SendScreenState extends State<SendScreen> {
  bool _dragging = false;

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final content = ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        const _ThisDeviceCard(),
        if (app.networkError != null) _Banner(text: app.networkError!, icon: Icons.warning_amber_rounded),
        if (app.localAddresses.isEmpty)
          const _Banner(
            icon: Icons.wifi_off_rounded,
            text: 'Aucun réseau Wi-Fi détecté. Connectez cet appareil au même Wi-Fi que l\'autre (ou au point d\'accès du téléphone).',
          ),
        const SectionTitle('Fichiers à envoyer'),
        const _SelectionCard(),
        SectionTitle(
          'Appareils à proximité',
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            if (app.scanning)
              const Padding(
                padding: EdgeInsets.only(right: 8),
                child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
              ),
            IconButton(
              tooltip: 'Actualiser',
              onPressed: app.scanning ? null : app.refreshDevices,
              icon: const Icon(Icons.refresh_rounded),
            ),
            TextButton.icon(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const AddDeviceScreen())),
              icon: const Icon(Icons.qr_code_2_rounded),
              label: const Text('Ajouter'),
            ),
          ]),
        ),
        const _DeviceList(),
      ],
    );
    if (!app.isDesktop) return content;
    return DropTarget(
      onDragDone: (d) {
        setState(() => _dragging = false);
        app.addPaths(d.files.map((f) => f.path).toList());
      },
      onDragEntered: (_) => setState(() => _dragging = true),
      onDragExited: (_) => setState(() => _dragging = false),
      child: Stack(children: [
        content,
        if (_dragging)
          Positioned.fill(
            child: IgnorePointer(
              child: Container(
                margin: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.12),
                  border: Border.all(color: Theme.of(context).colorScheme.primary, width: 3),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.file_download_rounded, size: 64, color: Theme.of(context).colorScheme.primary),
                    const SizedBox(height: 8),
                    Text('Déposez pour ajouter à l\'envoi', style: Theme.of(context).textTheme.headlineSmall),
                  ]),
                ),
              ),
            ),
          ),
      ]),
    );
  }
}

class _ThisDeviceCard extends StatelessWidget {
  const _ThisDeviceCard();
  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final t = Theme.of(context);
    final ip = app.localAddresses.isEmpty ? 'hors réseau' : app.localAddresses.map((a) => a.address.address).join(' • ');
    const fg = Colors.white;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [brandBlue, brandCyan], begin: Alignment.topLeft, end: Alignment.bottomRight),
        borderRadius: BorderRadius.circular(18),
      ),
      padding: const EdgeInsets.all(16),
      child: Row(children: [
        Container(
          width: 52,
          height: 52,
          decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(14)),
          child: Icon(app.isAndroid ? Icons.smartphone_rounded : Icons.computer_rounded, color: fg, size: 30),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(app.settings.deviceName, style: t.textTheme.titleLarge?.copyWith(color: fg, fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text('Prêt à recevoir • $ip', style: t.textTheme.bodyMedium?.copyWith(color: fg)),
            Text('Empreinte de sécurité : ${DeviceIdentity.shortFp(app.engine.identity.fingerprint)}',
                style: t.textTheme.bodySmall?.copyWith(color: fg.withValues(alpha: 0.8))),
          ]),
        ),
        const Icon(Icons.wifi_tethering_rounded, color: fg),
      ]),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.text, required this.icon});
  final String text;
  final IconData icon;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Card(
      color: cs.errorContainer,
      child: ListTile(
        leading: Icon(icon, color: cs.onErrorContainer),
        title: Text(text, style: TextStyle(color: cs.onErrorContainer)),
        trailing: TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const HelpScreen())),
          child: const Text('Aide'),
        ),
      ),
    );
  }
}

class _SelectionCard extends StatelessWidget {
  const _SelectionCard();
  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final t = Theme.of(context);
    final sel = app.selection;
    final buttons = Wrap(spacing: 8, runSpacing: 8, alignment: WrapAlignment.center, children: [
      FilledButton.icon(onPressed: app.pickFiles, icon: const Icon(Icons.upload_file_rounded), label: const Text('Envoyer des fichiers')),
      if (app.isAndroid)
        FilledButton.tonalIcon(onPressed: app.pickMedia, icon: const Icon(Icons.photo_library_outlined), label: const Text('Photos et vidéos')),
      FilledButton.tonalIcon(onPressed: app.pickFolder, icon: const Icon(Icons.create_new_folder_outlined), label: const Text('Dossier')),
    ]);
    return Card(
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: t.colorScheme.outlineVariant, width: 1.5, style: BorderStyle.solid),
        ),
        padding: const EdgeInsets.all(16),
        child: sel.isEmpty
            ? Column(children: [
                Icon(app.isDesktop ? Icons.file_download_outlined : Icons.add_circle_outline_rounded, size: 44, color: t.colorScheme.primary),
                const SizedBox(height: 8),
                Text(app.isDesktop ? 'Glissez-déposez vos fichiers ou dossiers ici' : 'Choisissez ce que vous voulez envoyer',
                    style: t.textTheme.titleMedium, textAlign: TextAlign.center),
                const SizedBox(height: 4),
                Text('Tous types de fichiers, sans limite de taille.', style: t.textTheme.bodySmall),
                const SizedBox(height: 14),
                buttons,
              ])
            : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  Expanded(
                    child: Text('${sel.length} fichier(s) • ${formatSize(app.selectionSize)}',
                        style: t.textTheme.titleMedium),
                  ),
                  TextButton.icon(onPressed: app.clearSelection, icon: const Icon(Icons.clear_all_rounded), label: const Text('Vider')),
                ]),
                const SizedBox(height: 6),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 220),
                  child: ListView.builder(
                    shrinkWrap: true,
                    itemCount: sel.length,
                    itemBuilder: (c, i) => ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(iconForFile(sel[i].relPath)),
                      title: Text(sel[i].relPath, overflow: TextOverflow.ellipsis),
                      subtitle: Text(formatSize(sel[i].size)),
                      trailing: IconButton(
                        tooltip: 'Retirer',
                        icon: const Icon(Icons.remove_circle_outline),
                        onPressed: () => app.removeSourceAt(i),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                buttons,
                const SizedBox(height: 10),
                Text('Touchez un appareil ci-dessous pour envoyer.',
                    textAlign: TextAlign.center, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.primary)),
              ]),
      ),
    );
  }
}

class _DeviceList extends StatelessWidget {
  const _DeviceList();
  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final list = app.devices;
    if (list.isEmpty) {
      return EmptyState(
        icon: Icons.radar_rounded,
        title: 'Recherche des appareils…',
        text: 'Ouvrez Transferys sur l\'autre appareil, connecté au même Wi-Fi. S\'il n\'apparaît pas, utilisez « Ajouter » (QR code ou adresse IP).',
        action: OutlinedButton.icon(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const HelpScreen())),
          icon: const Icon(Icons.help_outline_rounded),
          label: const Text('Il n\'apparaît pas ?'),
        ),
      );
    }
    return Column(children: [for (final d in list) _DeviceTile(d)]);
  }
}

class _DeviceTile extends StatelessWidget {
  const _DeviceTile(this.d);
  final DeviceEntry d;
  @override
  Widget build(BuildContext context) {
    final app = context.read<AppState>();
    final t = Theme.of(context);
    final status = [
      d.online ? 'En ligne' : 'Hors ligne',
      d.isTrusted ? 'De confiance' : 'Nouvel appareil : appairage au premier envoi',
    ].join(' • ');
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
        leading: PlatformAvatar(platform: d.platform, online: d.online),
        title: Text(d.name, style: t.textTheme.titleMedium),
        subtitle: Text(status),
        trailing: FilledButton.icon(
          onPressed: (d.online || d.trusted?.lastAddress != null) ? () => app.sendTo(d) : null,
          icon: Icon(d.isTrusted ? Icons.send_rounded : Icons.link_rounded, size: 18),
          label: Text(d.isTrusted || app.selection.isNotEmpty ? 'Envoyer' : 'Appairer'),
        ),
        onTap: () => app.sendTo(d),
      ),
    );
  }
}
