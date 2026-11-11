// Écran « Transferts » : envois et réceptions en cours et récents.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../platform/system.dart';
import '../app_state.dart';
import '../widgets.dart';

class TransfersScreen extends StatelessWidget {
  const TransfersScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final jobs = app.engine.jobs;
    if (jobs.isEmpty) {
      return const Center(
        child: EmptyState(
          icon: Icons.swap_vert_rounded,
          title: 'Aucun transfert en cours',
          text: 'Les envois et réceptions apparaîtront ici, avec leur progression.',
        ),
      );
    }
    final hasFinished = jobs.any((j) => !j.isActive);
    return ListView(padding: const EdgeInsets.fromLTRB(16, 12, 16, 32), children: [
      if (hasFinished)
        Align(
          alignment: Alignment.centerRight,
          child: TextButton.icon(
            onPressed: app.engine.clearFinishedJobs,
            icon: const Icon(Icons.cleaning_services_outlined),
            label: const Text('Retirer les transferts terminés'),
          ),
        ),
      for (final j in jobs)
        JobCard(
          key: ValueKey(j.id),
          job: j,
          onOpenFolder: (job) => openFolderPath(job.folder!),
        ),
    ]);
  }
}
