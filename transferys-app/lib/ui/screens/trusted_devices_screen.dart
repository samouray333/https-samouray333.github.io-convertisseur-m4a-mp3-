// Appareils de confiance : renommer ou retirer.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../security/identity.dart';
import '../app_state.dart';
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
          : ListView(padding: const EdgeInsets.all(16), children: [
              for (final d in list)
                Card(
                  child: ListTile(
                    leading: PlatformAvatar(platform: d.platform, online: app.engine.isOnline(d.id)),
                    title: Text(d.name),
                    subtitle: Text('Appairé le ${formatDate(d.pairedAt)}\nEmpreinte ${DeviceIdentity.shortFp(d.fingerprint)}'),
                    isThreeLine: true,
                    trailing: IconButton(
                      tooltip: 'Retirer',
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
                  ),
                ),
            ]),
    );
  }
}
