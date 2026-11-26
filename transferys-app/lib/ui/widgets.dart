// Composants réutilisables de l'interface.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/format.dart';
import '../core/models.dart';
import '../core/sorting.dart';
import '../transfer/job.dart';
import 'brand.dart';

/// Icône et teinte par catégorie (mêmes catégories que le tri automatique).
(IconData, Color) categoryStyle(String category) => switch (category) {
      'Photos' => (Icons.image_rounded, const Color(0xFF1E9E6A)),
      'Vidéos' => (Icons.movie_rounded, const Color(0xFF7C4DFF)),
      'Musique' => (Icons.music_note_rounded, const Color(0xFFE0457B)),
      'Documents' => (Icons.description_rounded, brandBlue),
      'Archives' => (Icons.folder_zip_rounded, const Color(0xFFD98A0B)),
      'Applications' => (Icons.apps_rounded, const Color(0xFF00897B)),
      _ => (Icons.insert_drive_file_rounded, const Color(0xFF6E7A94)),
    };

IconData iconForFile(String name) => categoryStyle(categoryFor(name)).$1;

IconData platformIcon(DevicePlatform p) => switch (p) {
      DevicePlatform.windows => Icons.computer_rounded,
      DevicePlatform.android => Icons.smartphone_rounded,
      DevicePlatform.linux => Icons.laptop_rounded,
      DevicePlatform.other => Icons.devices_other_rounded,
    };

/// Pastille de type de fichier (couleur = catégorie).
class FileBadge extends StatelessWidget {
  const FileBadge({super.key, required this.name, this.size = 38});
  final String name;
  final double size;
  @override
  Widget build(BuildContext context) {
    final (icon, color) = categoryStyle(categoryFor(name));
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: color.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(size * 0.3)),
      child: Icon(icon, color: color, size: size * 0.55),
    );
  }
}

class PlatformAvatar extends StatelessWidget {
  const PlatformAvatar({super.key, required this.platform, this.size = 44, this.online = true});
  final DevicePlatform platform;
  final double size;
  final bool online;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: online ? cs.primary : cs.surfaceContainerHigh, shape: BoxShape.circle),
      child: Icon(platformIcon(platform), size: size * 0.5, color: online ? cs.onPrimary : cs.outline),
    );
  }
}

/// Titre de section : sobre, en casse normale.
class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key, this.trailing});
  final String text;
  final Widget? trailing;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(6, 22, 6, 10),
        child: Row(children: [
          Expanded(child: Text(text, style: Theme.of(context).textTheme.titleLarge)),
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
    final cs = t.colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 36, horizontal: 24),
      child: Column(children: [
        Container(
          width: 84,
          height: 84,
          decoration: BoxDecoration(color: cs.primary.withValues(alpha: 0.10), shape: BoxShape.circle),
          child: Icon(icon, size: 40, color: cs.primary),
        ),
        const SizedBox(height: 16),
        Text(title, style: t.textTheme.titleLarge, textAlign: TextAlign.center),
        if (text.isNotEmpty) ...[
          const SizedBox(height: 6),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Text(text, style: t.textTheme.bodyMedium?.copyWith(color: cs.onSurfaceVariant), textAlign: TextAlign.center),
          ),
        ],
        if (action != null) ...[const SizedBox(height: 16), action!],
      ]),
    );
  }
}

Color statusColor(BuildContext context, TransferStatus s) {
  final cs = Theme.of(context).colorScheme;
  switch (s) {
    case TransferStatus.done:
      return okGreen;
    case TransferStatus.failed:
    case TransferStatus.rejected:
      return cs.error;
    case TransferStatus.cancelled:
    case TransferStatus.skipped:
      return cs.outline;
    case TransferStatus.paused:
    case TransferStatus.reconnecting:
      return warnAmber;
    default:
      return cs.primary;
  }
}

/// Anneau de progression avec le pourcentage (ou une icône d'état) au centre.
class ProgressRing extends StatelessWidget {
  const ProgressRing({super.key, required this.value, required this.color, this.size = 56, this.icon});
  final double? value;
  final Color color;
  final double size;
  final IconData? icon;
  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return SizedBox(
      width: size,
      height: size,
      child: Stack(alignment: Alignment.center, children: [
        CustomPaint(
          size: Size.square(size),
          painter: _RingPainter(value: value, color: color, track: t.colorScheme.outlineVariant.withValues(alpha: 0.7)),
        ),
        if (icon != null)
          Icon(icon, color: color, size: size * 0.42)
        else if (value != null)
          Text('${(value! * 100).floor()}', style: t.textTheme.titleMedium?.copyWith(color: color, fontWeight: FontWeight.w800)),
      ]),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({required this.value, required this.color, required this.track});
  final double? value;
  final Color color;
  final Color track;
  @override
  void paint(Canvas canvas, Size size) {
    const stroke = 5.0;
    final rect = Offset.zero & size;
    final r = rect.deflate(stroke / 2);
    canvas.drawArc(r, 0, 2 * math.pi, false, Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..color = track);
    final v = (value ?? 0.12).clamp(0.0, 1.0);
    if (v > 0) {
      canvas.drawArc(r, -math.pi / 2, 2 * math.pi * v, false, Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = stroke
        ..strokeCap = StrokeCap.round
        ..color = color);
    }
  }

  @override
  bool shouldRepaint(_RingPainter o) => o.value != value || o.color != color;
}

/// Carte d'un transfert : anneau de progression, vitesse, temps restant,
/// pause / reprise / annulation, détail par fichier.
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
    final cs = t.colorScheme;
    final send = j.direction == TransferDirection.send;
    final speed = j.bytesPerSecond;
    final eta = j.eta;
    final active = j.isActive;
    final cur = j.currentFile;
    final color = statusColor(context, j.status);
    final IconData? ringIcon = switch (j.status) {
      TransferStatus.done => Icons.check_rounded,
      TransferStatus.failed || TransferStatus.rejected => Icons.priority_high_rounded,
      TransferStatus.cancelled => Icons.close_rounded,
      TransferStatus.paused => Icons.pause_rounded,
      TransferStatus.reconnecting => Icons.wifi_find_rounded,
      _ => null,
    };
    final line2 = StringBuffer('${formatSize(j.transferredBytes)} sur ${formatSize(j.totalSize)}');
    if (j.status == TransferStatus.running && speed > 0) {
      line2.write(', ${formatSpeed(speed)}');
      if (eta != null) line2.write(', reste ${formatDuration(eta)}');
    }
    final statusText = j.remotePaused
        ? 'En pause sur ${j.peerName}'
        : (j.status == TransferStatus.waiting && send ? 'En attente d\'acceptation' : j.status.label);

    return Zone(
      padding: const EdgeInsets.fromLTRB(16, 16, 8, 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          ProgressRing(value: j.status == TransferStatus.waiting ? null : j.progress, color: color, icon: ringIcon),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(send ? Icons.north_east_rounded : Icons.south_west_rounded, size: 16, color: cs.onSurfaceVariant),
                const SizedBox(width: 4),
                Flexible(
                  child: Text('${send ? 'Vers' : 'De'} ${j.peerName}', style: t.textTheme.titleMedium, overflow: TextOverflow.ellipsis),
                ),
              ]),
              const SizedBox(height: 2),
              Text(
                '$statusText, ${j.doneCount}/${j.files.length} fichier${j.files.length > 1 ? 's' : ''}',
                style: t.textTheme.labelMedium?.copyWith(color: color),
              ),
              const SizedBox(height: 2),
              Text(line2.toString(), style: t.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
            ]),
          ),
          if (active && j.status != TransferStatus.waiting) ...[
            if (j.status == TransferStatus.paused && !j.remotePaused)
              IconButton.filledTonal(tooltip: 'Reprendre', onPressed: j.resume, icon: const Icon(Icons.play_arrow_rounded))
            else if (j.status != TransferStatus.paused)
              IconButton(tooltip: 'Mettre en pause', onPressed: j.pause, icon: const Icon(Icons.pause_rounded)),
          ],
          if (active) IconButton(tooltip: 'Annuler', onPressed: () => _confirmCancel(context), icon: const Icon(Icons.close_rounded)),
          if (!active && !send && j.folder != null && widget.onOpenFolder != null)
            IconButton.filledTonal(
              tooltip: 'Ouvrir le dossier',
              onPressed: () => widget.onOpenFolder!(j),
              icon: const Icon(Icons.folder_open_rounded),
            ),
        ]),
        if (cur != null && active)
          Padding(
            padding: const EdgeInsets.fromLTRB(70, 8, 8, 0),
            child: Text('En cours : ${cur.relPath}', style: t.textTheme.bodySmall, overflow: TextOverflow.ellipsis),
          ),
        if (j.error != null && j.status != TransferStatus.done)
          Container(
            margin: const EdgeInsets.fromLTRB(0, 12, 8, 0),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: (j.status == TransferStatus.reconnecting ? warnAmber : cs.error).withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(Radii.chip),
            ),
            child: Text(j.error!,
                style: t.textTheme.bodySmall?.copyWith(color: j.status == TransferStatus.reconnecting ? warnAmber : cs.error)),
          ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => setState(() => _expanded = !_expanded),
            icon: Icon(_expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded),
            label: Text(_expanded ? 'Masquer les fichiers' : 'Voir les fichiers'),
          ),
        ),
        if (_expanded)
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 340),
            child: ListView.builder(
              shrinkWrap: true,
              padding: const EdgeInsets.only(bottom: 8, right: 8),
              itemCount: j.files.length,
              itemBuilder: (c, i) {
                final f = j.files[i];
                final fc = statusColor(context, f.status);
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 5),
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    FileBadge(name: f.relPath, size: 32),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Row(children: [
                          Expanded(child: Text(f.relPath, overflow: TextOverflow.ellipsis, style: t.textTheme.titleSmall)),
                          const SizedBox(width: 8),
                          Text(
                            f.status == TransferStatus.running ? '${(f.progress * 100).toStringAsFixed(0)} %' : f.status.label,
                            style: t.textTheme.labelSmall?.copyWith(color: fc),
                          ),
                        ]),
                        const SizedBox(height: 4),
                        ClipRRect(
                          borderRadius: BorderRadius.circular(3),
                          child: LinearProgressIndicator(value: f.progress.clamp(0, 1).toDouble(), minHeight: 4, color: fc),
                        ),
                        const SizedBox(height: 2),
                        Text(formatSize(f.size), style: t.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
                        if (f.error != null && f.status == TransferStatus.failed)
                          Text(f.error!, style: t.textTheme.bodySmall?.copyWith(color: cs.error)),
                      ]),
                    ),
                  ]),
                );
              },
            ),
          ),
      ]),
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
