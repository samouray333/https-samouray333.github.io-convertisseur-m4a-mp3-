// Contenu du QR code de connexion : transferys://connect?...
import '../core/models.dart';

class QrPayload {
  QrPayload({
    required this.id,
    required this.name,
    required this.platform,
    required this.addresses,
    required this.port,
    required this.fingerprint,
  });

  final String id;
  final String name;
  final DevicePlatform platform;
  final List<String> addresses;
  final int port;
  final String fingerprint;

  String encode() => Uri(scheme: 'transferys', host: 'connect', queryParameters: {
        'v': '1',
        'id': id,
        'n': name,
        'p': platform.name,
        'ip': addresses.join(','),
        'port': '$port',
        'fp': fingerprint,
      }).toString();

  static QrPayload? tryParse(String raw) {
    try {
      final u = Uri.parse(raw.trim());
      if (u.scheme != 'transferys' || u.host != 'connect') return null;
      final q = u.queryParameters;
      final ips = (q['ip'] ?? '').split(',').where((e) => e.isNotEmpty).toList();
      if (q['id'] == null || q['fp'] == null || ips.isEmpty) return null;
      return QrPayload(
        id: q['id']!,
        name: q['n'] ?? 'Appareil',
        platform: platformFromString(q['p']),
        addresses: ips,
        port: int.tryParse(q['port'] ?? '') ?? 53518,
        fingerprint: q['fp']!,
      );
    } catch (_) {
      return null;
    }
  }
}
