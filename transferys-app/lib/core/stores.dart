// Appareils de confiance et historique des transferts.
import 'models.dart';
import 'storage.dart';

class TrustStore {
  TrustStore(String dataDir) : _file = JsonFile(joinData(dataDir, 'trusted_devices.json'));
  final JsonFile _file;
  final Map<String, TrustedDevice> _devices = {};

  Iterable<TrustedDevice> get all => _devices.values;
  TrustedDevice? get(String id) => _devices[id];

  Future<void> load() async {
    final j = await _file.read(fallback: const []);
    _devices.clear();
    if (j is List) {
      for (final e in j) {
        try {
          final d = TrustedDevice.fromJson((e as Map).cast<String, dynamic>());
          _devices[d.id] = d;
        } catch (_) {}
      }
    }
  }

  Future<void> put(TrustedDevice d) async {
    _devices[d.id] = d;
    await _save();
  }

  Future<void> remove(String id) async {
    _devices.remove(id);
    await _save();
  }

  Future<void> _save() => _file.write(_devices.values.map((d) => d.toJson()).toList());
}

class HistoryStore {
  HistoryStore(String dataDir) : _file = JsonFile(joinData(dataDir, 'history.json'));
  final JsonFile _file;
  final List<HistoryEntry> _entries = [];

  /// Nombre maximum d'entrées conservées.
  static const int maxEntries = 500;

  List<HistoryEntry> get entries => List.unmodifiable(_entries);

  Future<void> load() async {
    final j = await _file.read(fallback: const []);
    _entries.clear();
    if (j is List) {
      for (final e in j) {
        try {
          _entries.add(HistoryEntry.fromJson((e as Map).cast<String, dynamic>()));
        } catch (_) {}
      }
    }
  }

  Future<void> add(HistoryEntry e) async {
    _entries.insert(0, e);
    if (_entries.length > maxEntries) _entries.removeRange(maxEntries, _entries.length);
    await _file.write(_entries.map((e) => e.toJson()).toList());
  }

  Future<void> clear() async {
    _entries.clear();
    await _file.write(const []);
  }
}
