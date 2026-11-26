// Choix du dossier d'arrivée sur l'autre appareil, au moment d'envoyer.
//
// Proposés : son dossier de réception habituel, ou n'importe quel
// sous-dossier de ses dossiers partagés ouverts au dépôt.
import 'package:flutter/material.dart';

import '../../core/errors.dart';
import '../../core/models.dart';
import '../../transfer/fs_service.dart';
import '../app_state.dart';
import '../brand.dart';

class RemoteDestination {
  const RemoteDestination({this.share, this.path = '', required this.label});

  /// null = dossier de réception habituel de l'autre appareil.
  final String? share;
  final String path;
  final String label;
}

Future<RemoteDestination?> showDestinationPicker(BuildContext context, AppState app, TrustedDevice device) {
  return showDialog<RemoteDestination>(
    context: context,
    builder: (_) => _DestinationDialog(app: app, device: device),
  );
}

class _DestinationDialog extends StatefulWidget {
  const _DestinationDialog({required this.app, required this.device});
  final AppState app;
  final TrustedDevice device;
  @override
  State<_DestinationDialog> createState() => _DestinationDialogState();
}

class _DestinationDialogState extends State<_DestinationDialog> {
  List<RemoteRoot>? _roots;
  RemoteRoot? _root;
  final _path = <String>[];
  List<RemoteEntry> _dirs = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadRoots();
  }

  Future<void> _run(Future<void> Function() f) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await f();
    } on TransferysException catch (e) {
      _error = e.message;
    } catch (e) {
      _error = '$e';
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _loadRoots() => _run(() async {
        final all = await widget.app.engine.remoteRoots(widget.device.id);
        _roots = all.where((r) => r.writable).toList();
      });

  Future<void> _open(RemoteRoot r, List<String> path) => _run(() async {
        final l = await widget.app.engine.remoteList(widget.device.id, r.id, path.join('/'));
        _root = r;
        _path
          ..clear()
          ..addAll(path);
        _dirs = l.where((e) => e.isDir).toList();
      });

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final cs = t.colorScheme;
    final name = widget.device.name;
    final here = _root == null ? null : [_root!.name, ..._path].join(' / ');

    Widget body;
    if (_root == null) {
      final roots = _roots ?? const <RemoteRoot>[];
      body = ListView(shrinkWrap: true, children: [
        _Option(
          icon: Icons.download_rounded,
          title: 'Son dossier de réception habituel',
          subtitle: 'Rangé selon les réglages de $name.',
          onTap: () => Navigator.pop(context, RemoteDestination(label: 'dossier habituel de $name')),
          highlight: true,
        ),
        const SizedBox(height: 8),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.all(8),
            child: Text('Dossiers de $name inaccessibles : $_error', style: t.textTheme.bodySmall?.copyWith(color: cs.error)),
          )
        else if (!_loading && roots.isEmpty)
          Padding(
            padding: const EdgeInsets.all(8),
            child: Text(
              'Pour choisir un dossier précis, sur $name : Réglages, Dossiers partagés, ajoutez le dossier et activez « Dépôt ».',
              style: t.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant),
            ),
          ),
        for (final r in roots)
          _Option(icon: Icons.folder_shared_rounded, title: r.name, subtitle: 'Dossier partagé', onTap: () => _open(r, []), chevron: true),
      ]);
    } else {
      body = ListView(shrinkWrap: true, children: [
        if (_path.isNotEmpty || _root != null)
          _Option(
            icon: Icons.arrow_upward_rounded,
            title: 'Dossier parent',
            onTap: () => _path.isEmpty
                ? setState(() {
                    _root = null;
                    _dirs = const [];
                  })
                : _open(_root!, _path.sublist(0, _path.length - 1)),
          ),
        if (!_loading && _dirs.isEmpty)
          Padding(
            padding: const EdgeInsets.all(10),
            child: Text('Pas de sous-dossier ici.', style: t.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
          ),
        for (final d in _dirs)
          _Option(icon: Icons.folder_rounded, title: d.name, onTap: () => _open(_root!, [..._path, d.name]), chevron: true),
      ]);
    }

    return AlertDialog(
      title: Text('Où envoyer sur $name ?'),
      content: SizedBox(
        width: 460,
        height: 380,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (here != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              margin: const EdgeInsets.only(bottom: 8),
              decoration: BoxDecoration(color: cs.primary.withValues(alpha: 0.08), borderRadius: BorderRadius.circular(Radii.chip)),
              child: Row(children: [
                Icon(Icons.folder_open_rounded, color: cs.primary, size: 20),
                const SizedBox(width: 8),
                Expanded(child: Text(here, style: t.textTheme.titleSmall, overflow: TextOverflow.ellipsis)),
              ]),
            ),
          if (_loading) const LinearProgressIndicator(minHeight: 3),
          Expanded(child: body),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Annuler')),
        if (_root != null)
          FilledButton.icon(
            onPressed: () => Navigator.pop(
              context,
              RemoteDestination(share: _root!.id, path: _path.join('/'), label: here!),
            ),
            icon: const Icon(Icons.send_rounded),
            label: const Text('Envoyer ici'),
          ),
      ],
    );
  }
}

class _Option extends StatelessWidget {
  const _Option({required this.icon, required this.title, this.subtitle, required this.onTap, this.chevron = false, this.highlight = false});
  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;
  final bool chevron;
  final bool highlight;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: ListTile(
        tileColor: highlight ? cs.primary.withValues(alpha: 0.08) : null,
        leading: Icon(icon, color: cs.primary),
        title: Text(title),
        subtitle: subtitle == null ? null : Text(subtitle!),
        trailing: chevron ? const Icon(Icons.chevron_right_rounded) : null,
        onTap: onTap,
      ),
    );
  }
}
