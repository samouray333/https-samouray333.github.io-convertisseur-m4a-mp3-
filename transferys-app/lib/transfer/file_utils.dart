// Noms de fichiers : nettoyage des chemins reçus et gestion des doublons.
import 'dart:io';

import 'package:path/path.dart' as p;

const _reserved = {
  'con', 'prn', 'aux', 'nul', //
  'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
  'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
};

/// Nettoie un composant de chemin pour qu'il soit valide sous Windows ET
/// Android (caractères interdits, noms réservés, points finaux…).
String sanitizeComponent(String s) {
  var out = s.replaceAll(RegExp(r'[<>:"/\\|?*\x00-\x1F]'), '_').trim();
  while (out.endsWith('.') || out.endsWith(' ')) {
    out = out.substring(0, out.length - 1);
  }
  if (out.isEmpty) out = 'fichier';
  final base = out.split('.').first.toLowerCase();
  if (_reserved.contains(base)) out = '_$out';
  if (out.length > 200) {
    final ext = p.extension(out);
    out = out.substring(0, 200 - ext.length) + ext;
  }
  return out;
}

/// Transforme un chemin relatif envoyé par l'autre appareil en chemin sûr :
/// impossible de sortir du dossier de réception (pas de « .. », pas d'absolu).
List<String> sanitizeRelPath(String rel) {
  final parts = rel
      .split(RegExp(r'[\\/]+'))
      .where((c) => c.isNotEmpty && c != '.' && c != '..')
      .map(sanitizeComponent)
      .toList();
  return parts.isEmpty ? ['fichier'] : parts;
}

/// « photo.jpg » → « photo (1).jpg », « photo (2).jpg »… premier nom libre.
String uniquePath(String path) {
  if (!File(path).existsSync() && !Directory(path).existsSync()) return path;
  final dir = p.dirname(path);
  final ext = p.extension(path);
  final base = p.basenameWithoutExtension(path);
  for (var i = 1; i < 100000; i++) {
    final c = p.join(dir, '$base ($i)$ext');
    if (!File(c).existsSync() && !Directory(c).existsSync()) return c;
  }
  return p.join(dir, '$base (${DateTime.now().millisecondsSinceEpoch})$ext');
}

/// Déplace un fichier (renommage, ou copie + suppression si autre volume).
Future<File> moveFile(File src, String dest) async {
  await Directory(p.dirname(dest)).create(recursive: true);
  try {
    return await src.rename(dest);
  } on FileSystemException {
    final copy = await src.copy(dest);
    await src.delete();
    return copy;
  }
}
