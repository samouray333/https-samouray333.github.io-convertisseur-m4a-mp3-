// Points d'accroche spécifiques à chaque plateforme, utilisés par le moteur.
// L'implémentation par défaut sert aux tests (Linux) ; Android et Windows
// fournissent la leur.
import 'dart:io';

abstract class PlatformHooks {
  /// Espace libre (octets) sur le volume de [dir], ou null si inconnu.
  Future<int?> freeSpace(String dir);

  /// Un fichier vient d'être enregistré (Android : indexation dans la galerie).
  Future<void> fileSaved(String path) async {}

  /// Transfert en cours ou non (Android : service au premier plan).
  Future<void> transferActivity({required bool active, String? title, String? text, int? percent}) async {}

  /// Appelé au démarrage du réseau (Android : verrou multicast Wi-Fi).
  Future<void> networkStarted() async {}

  /// Accès à distance actif (Android : service au premier plan permanent).
  Future<void> remoteMode(bool active) async {}
}

class DefaultPlatformHooks extends PlatformHooks {
  @override
  Future<int?> freeSpace(String dir) async {
    if (!Platform.isLinux && !Platform.isMacOS) return null;
    try {
      final r = await Process.run('df', ['-Pk', dir]);
      final lines = (r.stdout as String).trim().split('\n');
      final cols = lines.last.split(RegExp(r'\s+'));
      return int.parse(cols[3]) * 1024;
    } catch (_) {
      return null;
    }
  }
}
