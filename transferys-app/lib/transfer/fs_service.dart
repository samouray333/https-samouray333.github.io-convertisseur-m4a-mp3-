// Accès aux dossiers partagés (explorateur à distance).
//
// Seuls les dossiers choisis dans les réglages sont visibles. Chaque chemin
// demandé est résolu puis vérifié : impossible d'en sortir (« .. », liens
// symboliques, chemins absolus).
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

import '../core/settings.dart';

String shareId(SharedFolder s) => sha1.convert(utf8.encode(s.path)).toString().substring(0, 12);

class FsException implements Exception {
  FsException(this.code, this.message);
  final String code; // not_found, forbidden, read_only
  final String message;
  @override
  String toString() => message;
}

class RemoteEntry {
  RemoteEntry({required this.name, required this.isDir, required this.size, required this.modified});
  final String name;
  final bool isDir;
  final int size;
  final DateTime modified;

  Map<String, Object?> toJson() => {'n': name, 'd': isDir, 's': size, 'm': modified.millisecondsSinceEpoch};
  factory RemoteEntry.fromJson(Map j) => RemoteEntry(
        name: j['n'] as String,
        isDir: j['d'] as bool,
        size: (j['s'] as num).toInt(),
        modified: DateTime.fromMillisecondsSinceEpoch((j['m'] as num).toInt()),
      );
}

class RemoteRoot {
  RemoteRoot({required this.id, required this.name, required this.writable});
  final String id;
  final String name;
  final bool writable;
  Map<String, Object?> toJson() => {'id': id, 'name': name, 'writable': writable};
  factory RemoteRoot.fromJson(Map j) =>
      RemoteRoot(id: j['id'] as String, name: j['name'] as String, writable: j['writable'] as bool? ?? false);
}

class FsService {
  FsService(this.shares);

  /// Lecture paresseuse : les réglages peuvent changer à tout moment.
  final List<SharedFolder> Function() shares;

  List<RemoteRoot> roots() => [
        for (final s in shares())
          if (Directory(s.path).existsSync()) RemoteRoot(id: shareId(s), name: s.name, writable: s.writable),
      ];

  SharedFolder _share(String id) {
    for (final s in shares()) {
      if (shareId(s) == id) return s;
    }
    throw FsException('not_found', 'Ce dossier n\'est plus partagé.');
  }

  /// Chemin absolu sûr pour [rel] dans le partage [id].
  String resolve(String id, String rel, {bool mustExist = true}) {
    final share = _share(id);
    final root = p.normalize(p.absolute(share.path));
    final parts = rel.split(RegExp(r'[\\/]+')).where((c) => c.isNotEmpty && c != '.').toList();
    if (parts.any((c) => c == '..')) throw FsException('forbidden', 'Chemin interdit.');
    final full = p.normalize(p.joinAll([root, ...parts]));
    if (full != root && !p.isWithin(root, full)) throw FsException('forbidden', 'Chemin interdit.');
    if (mustExist) {
      final type = FileSystemEntity.typeSync(full);
      if (type == FileSystemEntityType.notFound) throw FsException('not_found', 'Introuvable : $rel');
      // Lien symbolique qui sortirait du partage ?
      try {
        final real = File(full).resolveSymbolicLinksSync();
        final realRoot = Directory(root).resolveSymbolicLinksSync();
        if (real != realRoot && !p.isWithin(realRoot, real)) throw FsException('forbidden', 'Chemin interdit.');
      } on FileSystemException {
        // tant pis : le contrôle lexical a déjà été fait
      }
    }
    return full;
  }

  bool writable(String id) => _share(id).writable;

  Future<List<RemoteEntry>> list(String id, String rel) async {
    final dir = Directory(resolve(id, rel));
    final out = <RemoteEntry>[];
    try {
      await for (final e in dir.list(followLinks: false)) {
        final name = p.basename(e.path);
        if (name.startsWith('.transferys-partial')) continue;
        try {
          final st = await e.stat();
          final isDir = st.type == FileSystemEntityType.directory;
          if (!isDir && st.type != FileSystemEntityType.file) continue;
          out.add(RemoteEntry(name: name, isDir: isDir, size: isDir ? 0 : st.size, modified: st.modified));
        } catch (_) {}
      }
    } on FileSystemException catch (e) {
      throw FsException('forbidden', 'Dossier illisible : ${e.osError?.message ?? e.message}');
    }
    out.sort((a, b) {
      if (a.isDir != b.isDir) return a.isDir ? -1 : 1;
      return a.name.toLowerCase().compareTo(b.name.toLowerCase());
    });
    return out;
  }

  /// Fichiers d'un dossier, récursivement (pour télécharger un dossier entier).
  Future<List<(String rel, int size, DateTime modified)>> walk(String id, String rel) async {
    final base = resolve(id, rel);
    final type = FileSystemEntity.typeSync(base);
    if (type == FileSystemEntityType.file) {
      final f = File(base);
      return [(rel, await f.length(), await f.lastModified())];
    }
    final out = <(String, int, DateTime)>[];
    await for (final e in Directory(base).list(recursive: true, followLinks: false)) {
      if (e is! File) continue;
      if (e.path.contains(partialMarker)) continue;
      try {
        final st = await e.stat();
        final r = p.relative(e.path, from: resolve(id, ''));
        out.add((r.replaceAll('\\', '/'), st.size, st.modified));
      } catch (_) {}
    }
    out.sort((a, b) => a.$1.compareTo(b.$1));
    return out;
  }

  static const partialMarker = '.transferys-partial';

  static Future<Uint8List> readRange(String path, int offset, int len) async {
    final raf = await File(path).open();
    try {
      await raf.setPosition(offset);
      return await raf.read(len);
    } finally {
      await raf.close();
    }
  }

  static Future<String> sha256Of(String path) async => (await sha256.bind(File(path).openRead()).first).toString();
}
