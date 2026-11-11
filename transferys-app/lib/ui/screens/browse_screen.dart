// Écran « Parcourir » : explorer les dossiers partagés de l'autre appareil
// (à la maison en Wi-Fi comme à distance en 4G), télécharger, déposer.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/errors.dart';
import '../../core/format.dart';
import '../../core/models.dart';
import '../../transfer/file_source.dart';
import '../../transfer/fs_service.dart';
import '../../platform/android_bridge.dart';
import '../app_state.dart';
import '../widgets.dart';

class BrowseScreen extends StatelessWidget {
  const BrowseScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final trusted = app.engine.trust.all.toList()..sort((a, b) => a.name.compareTo(b.name));
    return ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 32), children: [
      const SectionTitle('Mes appareils'),
      if (trusted.isEmpty)
        const EmptyState(
          icon: Icons.folder_shared_outlined,
          title: 'Aucun appareil appairé',
          text: 'Appairez d\'abord un appareil depuis l\'onglet Envoyer. Vous pourrez ensuite parcourir ses dossiers partagés, ici ou à distance.',
        ),
      for (final t in trusted)
        Card(
          child: ListTile(
            leading: PlatformAvatar(platform: t.platform, online: app.engine.isOnline(t.id)),
            title: Text(t.name),
            subtitle: Text(_status(app, t)),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => RemoteBrowser(device: t))),
          ),
        ),
      const SectionTitle('Ce que je partage'),
      Card(
        child: ListTile(
          leading: const Icon(Icons.folder_outlined),
          title: Text(app.settings.shares.isEmpty
              ? 'Aucun dossier partagé'
              : app.settings.shares.map((s) => s.name).join(', ')),
          subtitle: const Text('Les dossiers que vos appareils de confiance peuvent parcourir.'),
          trailing: TextButton(onPressed: app.addShare, child: const Text('Ajouter')),
        ),
      ),
    ]);
  }

  static String _status(AppState app, TrustedDevice t) {
    if (app.devices.any((d) => d.id == t.id && d.peer != null)) return 'Sur ce réseau';
    if (app.engine.reachable.contains(t.id)) return 'Joignable à distance';
    return 'Hors ligne pour l\'instant (on réessaiera à l\'ouverture)';
  }
}

class RemoteBrowser extends StatefulWidget {
  const RemoteBrowser({super.key, required this.device});
  final TrustedDevice device;
  @override
  State<RemoteBrowser> createState() => _RemoteBrowserState();
}

class _RemoteBrowserState extends State<RemoteBrowser> {
  List<RemoteRoot>? _roots;
  RemoteRoot? _root;
  final _path = <String>[];
  List<RemoteEntry>? _entries;
  final _selected = <String>{};
  bool _loading = false;
  String? _error;

  String get _rel => _path.join('/');

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
        final app = context.read<AppState>();
        _roots = await app.engine.remoteRoots(widget.device.id);
        _root = null;
        _entries = null;
        _path.clear();
        _selected.clear();
      });

  Future<void> _open(RemoteRoot r, List<String> path) => _run(() async {
        final app = context.read<AppState>();
        final l = await app.engine.remoteList(widget.device.id, r.id, path.join('/'));
        _root = r;
        _path
          ..clear()
          ..addAll(path);
        _entries = l;
        _selected.clear();
      });

  Future<bool> _back() async {
    if (_root == null) return true;
    if (_path.isEmpty) {
      setState(() {
        _root = null;
        _entries = null;
        _selected.clear();
      });
    } else {
      await _open(_root!, _path.sublist(0, _path.length - 1));
    }
    return false;
  }

  Future<void> _download(List<String> names) async {
    final app = context.read<AppState>();
    final paths = [for (final n in names) _rel.isEmpty ? n : '$_rel/$n'];
    try {
      await app.engine.download(widget.device.id, _root!.id, paths);
      app.toast('Téléchargement lancé : suivez-le dans l\'onglet Transferts.');
      setState(_selected.clear);
    } on TransferysException catch (e) {
      app.showErrorDialog('Téléchargement impossible', e.message);
    }
  }

  Future<void> _uploadHere() async {
    final app = context.read<AppState>();
    final before = app.selection.length;
    if (app.isAndroid) {
      app.addSources(await AndroidBridge.pickFiles());
    } else {
      await app.pickFiles();
    }
    final picked = app.selection.sublist(before);
    if (picked.isEmpty) return;
    app.selection.removeRange(before, app.selection.length);
    try {
      await app.engine.send(widget.device.id, List<FileSource>.of(picked), share: _root!.id, path: _rel);
      app.toast('Envoi lancé vers « ${_root!.name}${_rel.isEmpty ? '' : '/$_rel'} ».');
    } on TransferysException catch (e) {
      app.showErrorDialog('Envoi impossible', e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final title = _root == null ? widget.device.name : (_path.isEmpty ? _root!.name : _path.last);
    final body = _buildBody(context);
    return PopScope(
      canPop: _root == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(title, overflow: TextOverflow.ellipsis),
          actions: [
            if (_selected.isNotEmpty)
              TextButton.icon(
                onPressed: () => _download(_selected.toList()),
                icon: const Icon(Icons.download_rounded),
                label: Text('Télécharger (${_selected.length})'),
              ),
            IconButton(
              tooltip: 'Actualiser',
              onPressed: _loading ? null : () => _root == null ? _loadRoots() : _open(_root!, List.of(_path)),
              icon: const Icon(Icons.refresh_rounded),
            ),
          ],
          bottom: _loading ? const PreferredSize(preferredSize: Size.fromHeight(3), child: LinearProgressIndicator(minHeight: 3)) : null,
        ),
        floatingActionButton: _root != null && _root!.writable
            ? FloatingActionButton.extended(
                onPressed: _uploadHere,
                icon: const Icon(Icons.upload_rounded),
                label: const Text('Envoyer ici'),
              )
            : null,
        body: Column(children: [
          if (_root != null)
            Container(
              width: double.infinity,
              color: t.colorScheme.surfaceContainerLow,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(children: [
                  TextButton(onPressed: () => _open(_root!, []), child: Text(_root!.name)),
                  for (var i = 0; i < _path.length; i++) ...[
                    const Icon(Icons.chevron_right, size: 18),
                    TextButton(onPressed: () => _open(_root!, _path.sublist(0, i + 1)), child: Text(_path[i])),
                  ],
                  if (!_root!.writable)
                    Padding(
                      padding: const EdgeInsets.only(left: 8),
                      child: Chip(label: const Text('Lecture seule'), visualDensity: VisualDensity.compact, avatar: const Icon(Icons.lock_outline, size: 16)),
                    ),
                ]),
              ),
            ),
          Expanded(child: body),
        ]),
      ),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_error != null) {
      return Center(
        child: SingleChildScrollView(
          child: EmptyState(
            icon: Icons.cloud_off_rounded,
            title: 'Connexion impossible',
            text: _error!,
            action: FilledButton.icon(
              onPressed: () => _root == null ? _loadRoots() : _open(_root!, List.of(_path)),
              icon: const Icon(Icons.refresh),
              label: const Text('Réessayer'),
            ),
          ),
        ),
      );
    }
    if (_root == null) {
      final roots = _roots;
      if (roots == null) return const SizedBox();
      if (roots.isEmpty) {
        return EmptyState(
          icon: Icons.folder_off_outlined,
          title: '${widget.device.name} ne partage aucun dossier',
          text: 'Sur ${widget.device.name} : Réglages > Dossiers partagés > Ajouter.',
        );
      }
      return ListView(padding: const EdgeInsets.all(12), children: [
        for (final r in roots)
          Card(
            child: ListTile(
              leading: Icon(r.writable ? Icons.folder_shared_rounded : Icons.folder_rounded, size: 32),
              title: Text(r.name),
              subtitle: Text(r.writable ? 'Lecture et dépôt de fichiers' : 'Lecture seule'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => _open(r, []),
            ),
          ),
      ]);
    }
    final entries = _entries ?? const <RemoteEntry>[];
    if (entries.isEmpty && !_loading) {
      return const EmptyState(icon: Icons.folder_open_outlined, title: 'Dossier vide', text: '');
    }
    return ListView.builder(
      padding: const EdgeInsets.only(bottom: 96),
      itemCount: entries.length,
      itemBuilder: (c, i) {
        final e = entries[i];
        final sel = _selected.contains(e.name);
        return ListTile(
          leading: Icon(e.isDir ? Icons.folder_rounded : iconForFile(e.name),
              color: e.isDir ? Theme.of(context).colorScheme.primary : null),
          title: Text(e.name, overflow: TextOverflow.ellipsis),
          subtitle: Text(e.isDir ? 'Dossier' : '${formatSize(e.size)} • ${formatDate(e.modified)}'),
          selected: sel,
          trailing: Row(mainAxisSize: MainAxisSize.min, children: [
            if (!e.isDir)
              IconButton(tooltip: 'Télécharger', icon: const Icon(Icons.download_rounded), onPressed: () => _download([e.name])),
            Checkbox(
              value: sel,
              onChanged: (v) => setState(() => v == true ? _selected.add(e.name) : _selected.remove(e.name)),
            ),
          ]),
          onTap: () {
            if (_selected.isNotEmpty) {
              setState(() => sel ? _selected.remove(e.name) : _selected.add(e.name));
            } else if (e.isDir) {
              _open(_root!, [..._path, e.name]);
            } else {
              _download([e.name]);
            }
          },
          onLongPress: () => setState(() => sel ? _selected.remove(e.name) : _selected.add(e.name)),
        );
      },
    );
  }
}
