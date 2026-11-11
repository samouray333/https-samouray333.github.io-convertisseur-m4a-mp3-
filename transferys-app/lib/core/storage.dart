// Persistance simple en fichiers JSON (écriture atomique).
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;

class JsonFile {
  JsonFile(this.path);
  final String path;

  /// Écritures sérialisées : deux transferts qui se terminent en même temps
  /// ne doivent pas se marcher dessus sur le fichier temporaire.
  Future<void> _queue = Future.value();

  /// Lit le fichier, ou renvoie [fallback] s'il n'existe pas / est corrompu.
  Future<dynamic> read({dynamic fallback}) async {
    try {
      final f = File(path);
      if (!await f.exists()) return fallback;
      return jsonDecode(await f.readAsString());
    } catch (_) {
      // Fichier corrompu (coupure de courant…) : on repart de zéro plutôt que planter.
      return fallback;
    }
  }

  /// Écrit via un fichier temporaire puis renommage, pour ne jamais laisser
  /// un JSON à moitié écrit.
  Future<void> write(Object? data) {
    final next = _queue.then((_) => _write(data));
    _queue = next.catchError((_) {});
    return next;
  }

  Future<void> _write(Object? data) async {
    final f = File(path);
    await f.parent.create(recursive: true);
    final tmp = File('$path.tmp');
    await tmp.writeAsString(const JsonEncoder.withIndent(' ').convert(data), flush: true);
    if (await f.exists()) {
      try {
        await f.delete();
      } catch (_) {}
    }
    await tmp.rename(path);
  }
}

String joinData(String dataDir, String name) => p.join(dataDir, name);
