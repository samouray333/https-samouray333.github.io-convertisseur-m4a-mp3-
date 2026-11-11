// Réglages de l'application (nom, dossier de réception, thème, etc.).
import 'models.dart';
import 'storage.dart';

/// Dossier partagé pour l'accès à distance.
class SharedFolder {
  SharedFolder({required this.path, required this.name, this.writable = false});
  final String path;
  String name;

  /// L'autre appareil peut y déposer des fichiers.
  bool writable;

  Map<String, dynamic> toJson() => {'path': path, 'name': name, 'writable': writable};
  factory SharedFolder.fromJson(Map<String, dynamic> j) =>
      SharedFolder(path: j['path'] as String, name: j['name'] as String? ?? 'Dossier', writable: j['writable'] as bool? ?? false);
}

class Settings {
  Settings({
    required this.deviceName,
    required this.receiveDir,
    this.themeMode = 'system',
    this.confirmBeforeReceive = true,
    this.duplicateMode = DuplicateMode.rename,
    this.autoStart = false,
    this.minimizeToTray = true,
    this.explorerMenu = true,
    this.onboardingDone = false,
    this.port = defaultPort,
    this.remoteAccess = false,
    List<SharedFolder>? shares,
  }) : shares = shares ?? [];

  static const int defaultPort = 53518;

  String deviceName;
  String receiveDir;

  /// 'system', 'light' ou 'dark'.
  String themeMode;
  bool confirmBeforeReceive;
  DuplicateMode duplicateMode;

  /// Windows : lancer au démarrage de la session.
  bool autoStart;

  /// Windows : fermer la fenêtre = rester dans la zone de notification.
  bool minimizeToTray;

  /// Windows : entrée « Envoyer avec Transferys » dans le clic droit.
  bool explorerMenu;
  bool onboardingDone;
  int port;

  /// Accès à distance (4G) : PC = ouverture du port sur la box ;
  /// téléphone = rester joignable par le PC.
  bool remoteAccess;

  /// Dossiers que les appareils de confiance peuvent parcourir.
  List<SharedFolder> shares;

  Map<String, dynamic> toJson() => {
        'deviceName': deviceName,
        'receiveDir': receiveDir,
        'themeMode': themeMode,
        'confirmBeforeReceive': confirmBeforeReceive,
        'duplicateMode': duplicateMode.name,
        'autoStart': autoStart,
        'minimizeToTray': minimizeToTray,
        'explorerMenu': explorerMenu,
        'onboardingDone': onboardingDone,
        'port': port,
        'remoteAccess': remoteAccess,
        'shares': shares.map((e) => e.toJson()).toList(),
      };

  static Settings fromJson(Map<String, dynamic> j, Settings defaults) => Settings(
        deviceName: (j['deviceName'] as String?)?.trim().isNotEmpty == true
            ? j['deviceName'] as String
            : defaults.deviceName,
        receiveDir: (j['receiveDir'] as String?)?.isNotEmpty == true
            ? j['receiveDir'] as String
            : defaults.receiveDir,
        themeMode: j['themeMode'] as String? ?? defaults.themeMode,
        confirmBeforeReceive: j['confirmBeforeReceive'] as bool? ?? true,
        duplicateMode: duplicateModeFromString(j['duplicateMode'] as String?),
        autoStart: j['autoStart'] as bool? ?? false,
        minimizeToTray: j['minimizeToTray'] as bool? ?? true,
        explorerMenu: j['explorerMenu'] as bool? ?? true,
        onboardingDone: j['onboardingDone'] as bool? ?? false,
        port: (j['port'] as num?)?.toInt() ?? defaultPort,
        remoteAccess: j['remoteAccess'] as bool? ?? false,
        shares: ((j['shares'] as List?) ?? const [])
            .map((e) => SharedFolder.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
      );
}

class SettingsStore {
  SettingsStore(String dataDir) : _file = JsonFile(joinData(dataDir, 'settings.json'));
  final JsonFile _file;

  Future<Settings> load(Settings defaults) async {
    final j = await _file.read();
    if (j is Map) return Settings.fromJson(j.cast<String, dynamic>(), defaults);
    return defaults;
  }

  Future<void> save(Settings s) => _file.write(s.toJson());
}
