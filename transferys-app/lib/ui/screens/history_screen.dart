// Écran « Historique » : date, appareil, fichiers, taille, statut, avec
// « Ouvrir le fichier » et « Ouvrir le dossier ».
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../../core/models.dart';
import '../../platform/android_bridge.dart';
import '../../platform/system.dart';
import '../app_state.dart';
import '../widgets.dart';

class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final entries = app.engine.history.entries;
    if (entries.isEmpty) {
      return const Center(
        child: EmptyState(icon: Icons.history_rounded, title: 'Historique vide', text: 'Vos transferts terminés apparaîtront ici.'),
      );
    }
    return ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
      Align(
        alignment: Alignment.centerRight,
        child: TextButton.icon(
          onPressed: () async {
            final ok = await showDialog<bool>(
              context: context,
              builder: (c) => AlertDialog(
                title: const Text('Effacer l\'historique ?'),
                content: const Text('Les fichiers reçus ne sont pas supprimés, seulement la liste.'),
                actions: [
                  TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Annuler')),
                  FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Effacer')),
                ],
              ),
            );
            if (ok == true) {
              await app.engine.history.clear();
              app.setTab(app.tab);
            }
          },
          icon: const Icon(Icons.delete_sweep_outlined),
          label: const Text('Effacer'),
        ),
      ),
      for (final e in entries) _HistoryTile(e),
    ]);
  }
}

class _HistoryTile extends StatelessWidget {
  const _HistoryTile(this.e);
  final HistoryEntry e;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final send = e.direction == TransferDirection.send;
    final n = e.files.length;
    final title = n == 1 ? p.basename(e.files.first.name) : '$n fichiers';
    return Card(
      child: ExpansionTile(
        shape: const Border(),
        leading: CircleAvatar(
          backgroundColor: statusColor(context, e.status).withValues(alpha: 0.15),
          child: Icon(send ? Icons.north_east_rounded : Icons.south_west_rounded, color: statusColor(context, e.status)),
        ),
        title: Text(title, overflow: TextOverflow.ellipsis),
        subtitle: Text(
          '${send ? 'Envoyé à' : 'Reçu de'} ${e.peerName} • ${formatSize(e.totalSize)}\n${formatDate(e.date)} • ${e.status.label}',
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        children: [
          if (e.error != null && e.status != TransferStatus.done)
            Align(
              alignment: Alignment.centerLeft,
              child: Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(e.error!, style: TextStyle(color: t.colorScheme.error)),
              ),
            ),
          for (final f in e.files.take(50))
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: Icon(iconForFile(f.name)),
              title: Text(f.path != null ? p.basename(f.path!) : f.name, overflow: TextOverflow.ellipsis),
              subtitle: Text('${formatSize(f.size)} • ${f.status.label}'),
              trailing: f.path != null && File(f.path!).existsSync()
                  ? Row(mainAxisSize: MainAxisSize.min, children: [
                      IconButton(
                        tooltip: 'Ouvrir le fichier',
                        icon: const Icon(Icons.open_in_new_rounded),
                        onPressed: () async {
                          final ok = await openFilePath(f.path!);
                          if (!ok && context.mounted) context.read<AppState>().toast('Aucune application ne sait ouvrir ce fichier.');
                        },
                      ),
                      if (Platform.isAndroid)
                        IconButton(
                          tooltip: 'Partager',
                          icon: const Icon(Icons.share_outlined),
                          onPressed: () => AndroidBridge.shareFile(f.path!),
                        ),
                    ])
                  : null,
            ),
          if (e.files.length > 50) Text('… et ${e.files.length - 50} autre(s)'),
          if (!send && e.folder != null)
            Align(
              alignment: Alignment.centerRight,
              child: OutlinedButton.icon(
                onPressed: () {
                  final first = e.files.map((f) => f.path).whereType<String>().firstOrNull;
                  openFolderPath(first != null ? p.dirname(first) : e.folder!, selectFile: first);
                },
                icon: const Icon(Icons.folder_open_rounded),
                label: const Text('Ouvrir le dossier'),
              ),
            ),
        ],
      ),
    );
  }
}
