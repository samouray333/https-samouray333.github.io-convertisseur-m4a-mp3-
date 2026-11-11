// Réglages de l'application (nom, dossier de réception, thème, etc.).
import 'models.dart';
import 'storage.dart';

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
  });

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
