// Composants réutilisables de l'interface.
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;

import '../core/format.dart';
import '../core/models.dart';
import '../transfer/job.dart';

IconData iconForFile(String name) {
  final ext = p.extension(name).toLowerCase();
  const img = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.bmp', '.svg', '.raw', '.dng'};
  const vid = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.3gp', '.wmv'};
  const aud = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma'};
  const arc = {'.zip', '.rar', '.7z', '.tar', '.gz', '.xz'};
  const doc = {'.doc', '.docx', '.odt', '.txt', '.rtf', '.md'};
  if (img.contains(ext)) return Icons.image_outlined;
  if (vid.contains(ext)) return Icons.movie_outlined;
  if (aud.contains(ext)) return Icons.music_note_outlined;
  if (arc.contains(ext)) return Icons.folder_zip_outlined;
  if (ext == '.pdf') return Icons.picture_as_pdf_outlined;
  if (ext == '.apk') return Icons.android;
  if (ext == '.xlsx' || ext == '.xls' || ext == '.csv' || ext == '.ods') return Icons.table_chart_outlined;
  if (doc.contains(ext)) return Icons.description_outlined;
  return Icons.insert_drive_file_outlined;
}

class PlatformAvatar extends StatelessWidget {
  const PlatformAvatar({super.key, required this.platform, this.size = 40, this.online = true});
  final DevicePlatform platform;
  final double size;
  final bool online;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final icon = switch (platform) {
      DevicePlatform.windows => Icons.computer_rounded,
      DevicePlatform.android => Icons.smartphone_rounded,
      DevicePlatform.linux => Icons.laptop_rounded,
      DevicePlatform.other => Icons.devices_other_rounded,
    };
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: online ? cs.primaryContainer : cs.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(size * 0.3),
      ),
      child: Icon(icon, size: size * 0.55, color: online ? cs.onPrimaryContainer : cs.onSurfaceVariant),
    );
  }
}

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});
  final String text;
  final Widget? trailing;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 18, 4, 8),
        child: Row(children: [
          Expanded(
            child: Text(text,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      color: Theme.of(context).colorScheme.primary,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.3,
                    )),
          ),
          if (trailing != null) trailing!,
        ]),
      );
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, required this.text, this.action});
  final IconData icon;
  final String title;
  final String text;
  final Widget? action;
  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 16),
      child: Column(children: [
        Icon(icon, size: 52, color: t.colorScheme.outline),
        const SizedBox(height: 12),
        Text(title, style: t.textTheme.titleMedium, textAlign: TextAlign.center),
        const SizedBox(height: 6),
        Text(text, style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant), textAlign: TextAlign.center),
        if (action != null) ...[const SizedBox(height: 14), action!],
      ]),
    );
  }
}

Color statusColor(BuildContext context, TransferStatus s) {
  final cs = Theme.of(context).colorScheme;
  switch (s) {
    case TransferStatus.done:
      return Colors.green.shade600;
    case TransferStatus.failed:
    case TransferStatus.rejected:
      return cs.error;
    case TransferStatus.cancelled:
    case TransferStatus.skipped:
      return cs.outline;
    case TransferStatus.paused:
    case TransferStatus.reconnecting:
      return Colors.orange.shade700;
    default:
      return cs.primary;
  }
}

/// Carte d'un transfert : progression globale et par fichier, vitesse,
/// temps restant, pause / reprise / annulation.
class JobCard extends StatefulWidget {
  const JobCard({super.key, required this.job, this.onOpenFolder});
  final TransferJob job;
  final void Function(TransferJob job)? onOpenFolder;
  @override
  State<JobCard> createState() => _JobCardState();
}

class _JobCardState extends State<JobCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final j = widget.job;
    final t = Theme.of(context);
    final send = j.direction == TransferDirection.send;
    final speed = j.bytesPerSecond;
    final eta = j.eta;
    final active = j.isActive;
    final cur = j.currentFile;
    final subtitle = StringBuffer('${j.doneCount}/${j.files.length} fichier(s) • ${formatSize(j.transferredBytes)} / ${formatSize(j.totalSize)}');
    if (j.status == TransferStatus.running && speed > 0) {
      subtitle.write(' • ${formatSpeed(speed)}');
      if (eta != null) subtitle.write(' • reste ${formatDuration(eta)}');
    }
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 8, 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(send ? Icons.north_east_rounded : Icons.south_west_rounded, color: t.colorScheme.primary),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${send ? 'Envoi vers' : 'Réception depuis'} ${j.peerName}',
                    style: t.textTheme.titleMedium, overflow: TextOverflow.ellipsis),
                const SizedBox(height: 2),
                Text(
                  j.remotePaused ? 'En pause (demandée par ${j.peerName})' : j.status.label,
                  style: t.textTheme.labelLarge?.copyWith(color: statusColor(context, j.status)),
                ),
              ]),
            ),
            if (active && j.status != TransferStatus.waiting) ...[
              if (j.status == TransferStatus.paused && !j.remotePaused)
                IconButton(tooltip: 'Reprendre', onPressed: j.resume, icon: const Icon(Icons.play_arrow_rounded))
              else if (j.status != TransferStatus.paused)
                IconButton(tooltip: 'Mettre en pause', onPressed: j.pause, icon: const Icon(Icons.pause_rounded)),
            ],
            if (active)
              IconButton(tooltip: 'Annuler', onPressed: () => _confirmCancel(context), icon: const Icon(Icons.close_rounded)),
            if (!active && !send && j.folder != null && widget.onOpenFolder != null)
              IconButton(tooltip: 'Ouvrir le dossier', onPressed: () => widget.onOpenFolder!(j), icon: const Icon(Icons.folder_open_rounded)),
          ]),
          const SizedBox(height: 10),
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: j.status == TransferStatus.waiting ? null : j.progress.clamp(0, 1).toDouble(),
                minHeight: 8,
                color: statusColor(context, j.status),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Text(subtitle.toString(), style: t.textTheme.bodySmall),
          if (cur != null && active)
            Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Text('Fichier en cours : ${cur.relPath} (${(cur.progress * 100).toStringAsFixed(0)} %)',
                  style: t.textTheme.bodySmall, overflow: TextOverflow.ellipsis),
            ),
          if (j.error != null && j.status != TransferStatus.done)
            Padding(
              padding: const EdgeInsets.only(top: 6, right: 8),
              child: Text(j.error!,
                  style: t.textTheme.bodySmall?.copyWith(
                      color: j.status == TransferStatus.reconnecting ? Colors.orange.shade800 : t.colorScheme.error)),
            ),
          if (j.status == TransferStatus.waiting && send)
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text('En attente d\'acceptation sur ${j.peerName}…', style: t.textTheme.bodySmall),
            ),
          TextButton.icon(
            onPressed: () => setState(() => _expanded = !_expanded),
            icon: Icon(_expanded ? Icons.expand_less : Icons.expand_more),
            label: Text(_expanded ? 'Masquer les fichiers' : 'Voir les fichiers'),
          ),
          if (_expanded)
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: j.files.length,
                itemBuilder: (c, i) {
                  final f = j.files[i];
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(children: [
                      Icon(iconForFile(f.relPath), size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(f.relPath, overflow: TextOverflow.ellipsis, style: t.textTheme.bodyMedium),
                          const SizedBox(height: 3),
                          LinearProgressIndicator(value: f.progress.clamp(0, 1).toDouble(), minHeight: 3, color: statusColor(context, f.status)),
                          if (f.error != null && f.status == TransferStatus.failed)
                            Padding(
                              padding: const EdgeInsets.only(top: 2),
                              child: Text(f.error!, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.error)),
                            ),
                        ]),
                      ),
                      const SizedBox(width: 10),
                      SizedBox(
                        width: 110,
                        child: Text(
                          f.status == TransferStatus.running ? '${(f.progress * 100).toStringAsFixed(0)} % de ${formatSize(f.size)}' : '${f.status.label} • ${formatSize(f.size)}',
                          style: t.textTheme.bodySmall?.copyWith(color: statusColor(context, f.status)),
                          textAlign: TextAlign.right,
                        ),
                      ),
                      const SizedBox(width: 8),
                    ]),
                  );
                },
              ),
            ),
        ]),
      ),
    );
  }

  Future<void> _confirmCancel(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Annuler le transfert ?'),
        content: const Text('Les fichiers déjà terminés sont conservés. Le fichier en cours sera supprimé.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Continuer')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Annuler le transfert')),
        ],
      ),
    );
    if (ok == true) widget.job.cancel();
  }
}
