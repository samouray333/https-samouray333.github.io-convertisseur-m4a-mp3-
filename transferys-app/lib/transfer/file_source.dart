// Source d'un fichier à envoyer. Abstraite pour gérer à la fois les fichiers
// classiques (Windows) et les contenus Android (content://) sans copie.
import 'dart:io';

import 'package:path/path.dart' as p;

abstract class FileSource {
  /// Chemin relatif reçu par l'autre appareil (ex. « Vacances/IMG_001.jpg »).
  String get relPath;
  int get size;
  DateTime get modified;

  /// Ouvre le fichier en lecture.
  Future<RandomAccessFile> open();

  /// Libère les ressources natives éventuelles (descripteur Android).
  Future<void> release() async {}
}

class LocalFileSource extends FileSource {
  LocalFileSource(this.path, {String? relPath, int? size, DateTime? modified})
      : relPath = relPath ?? p.basename(path),
        size = size ?? File(path).lengthSync(),
        modified = modified ?? File(path).lastModifiedSync();

  final String path;
  @override
  final String relPath;
  @override
  final int size;
  @override
  final DateTime modified;

  @override
  Future<RandomAccessFile> open() => File(path).open(mode: FileMode.read);
}

/// Développe une liste de chemins (fichiers et dossiers) en sources, en
/// conservant l'arborescence des dossiers.
Future<List<FileSource>> expandLocalPaths(List<String> paths) async {
  final out = <FileSource>[];
  for (final raw in paths) {
    final type = await FileSystemEntity.type(raw, followLinks: true);
    if (type == FileSystemEntityType.file) {
      out.add(LocalFileSource(raw));
    } else if (type == FileSystemEntityType.directory) {
      final root = Directory(raw);
      final parent = p.dirname(root.absolute.path);
      final files = <File>[];
      try {
        await for (final e in root.list(recursive: true, followLinks: false)) {
          if (e is File) files.add(e);
        }
      } on FileSystemException {
        // sous-dossier illisible : on envoie le reste
      }
      files.sort((a, b) => a.path.compareTo(b.path));
      for (final f in files) {
        try {
          final rel = p.relative(f.absolute.path, from: parent).replaceAll('\\', '/');
          out.add(LocalFileSource(f.path, relPath: rel));
        } catch (_) {}
      }
    }
  }
  return out;
}
