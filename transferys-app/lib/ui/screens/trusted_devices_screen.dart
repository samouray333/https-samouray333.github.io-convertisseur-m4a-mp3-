// Appareils de confiance : acceptation automatique, dossier attitré, retrait.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../core/models.dart';
import '../../security/identity.dart';
import '../app_state.dart';
import '../brand.dart';
import '../widgets.dart';

class TrustedDevicesScreen extends StatelessWidget {
  const TrustedDevicesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final list = app.engine.trust.all.toList()..sort((a, b) => a.name.compareTo(b.name));
    return Scaffold(
      appBar: AppBar(title: const Text('Appareils de confiance')),
      body: list.isEmpty
          ? const Center(
              child: EmptyState(
                icon: Icons.devices_outlined,
                title: 'Aucun appareil de confiance',
                text: 'Un appareil devient de confiance après l\'appairage par code à 6 chiffres.',
              ),
            )
          : Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 760),
                child: ListView(padding: const EdgeInsets.all(16), children: [for (final d in list) _DeviceZone(d)]),
              ),
            ),
    );
  }
}

class _DeviceZone extends StatelessWidget {
  const _DeviceZone(this.d);
  final TrustedDevice d;

  @override
  Widget build(BuildContext context) {
    final app = context.read<AppState>();
    final t = Theme.of(context);
    final cs = t.colorScheme;
    return Zone(
      padding: const EdgeInsets.fromLTRB(16, 14, 8, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          PlatformAvatar(platform: d.platform, online: app.engine.isOnline(d.id)),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(d.name, style: t.textTheme.titleMedium),
              Text('Appairé le ${formatDate(d.pairedAt)}, empreinte ${DeviceIdentity.shortFp(d.fingerprint)}',
                  style: t.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
            ]),
          ),
          IconButton(
            tooltip: 'Retirer cet appareil',
            icon: const Icon(Icons.link_off_rounded),
            onPressed: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (c) => AlertDialog(
                  title: Text('Retirer ${d.name} ?'),
                  content: const Text('Il ne pourra plus vous envoyer de fichiers sans un nouvel appairage.'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                    FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Retirer')),
                  ],
                ),
              );
              if (ok == true) await app.engine.removeTrusted(d.id);
            },
          ),
        ]),
        const SizedBox(height: 6),
        SwitchListTile(
          contentPadding: const EdgeInsets.only(left: 4, right: 8),
          secondary: const Icon(Icons.bolt_rounded),
          title: const Text('Toujours accepter'),
          subtitle: Text(d.autoAccept ? 'Ses envois arrivent sans confirmation.' : 'Confirmation demandée à chaque envoi.'),
          value: d.autoAccept,
          onChanged: (v) => app.engine.setAutoAccept(d.id, v),
        ),
        ListTile(
          contentPadding: const EdgeInsets.only(left: 4, right: 8),
          leading: const Icon(Icons.folder_rounded),
          title: const Text('Dossier de réception'),
          subtitle: Text(
            d.receiveDir ?? 'Dossier habituel (${app.settings.receiveDir})',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            if (d.receiveDir != null)
              IconButton(
                tooltip: 'Revenir au dossier habituel',
                icon: const Icon(Icons.undo_rounded),
                onPressed: () => app.engine.setDeviceFolder(d.id, null),
              ),
            TextButton(
              onPressed: () async {
                final dir = await app.chooseReceiveDir();
                if (dir != null) await app.engine.setDeviceFolder(d.id, dir);
              },
              child: const Text('Changer'),
            ),
          ]),
        ),
      ]),
    );
  }
}
