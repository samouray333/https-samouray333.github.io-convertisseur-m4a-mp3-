// Outils réseau : adresses locales, même sous-réseau, adresses de broadcast.
import 'dart:io';

class LocalAddress {
  LocalAddress(this.interfaceName, this.address);
  final String interfaceName;
  final InternetAddress address;
}

/// Adresses IPv4 privées des interfaces actives (Wi-Fi, Ethernet, point d'accès).
Future<List<LocalAddress>> localIPv4Addresses() async {
  try {
    final list = await NetworkInterface.list(type: InternetAddressType.IPv4, includeLoopback: false);
    final out = <LocalAddress>[];
    for (final ni in list) {
      final name = ni.name.toLowerCase();
      // Interfaces virtuelles sans intérêt pour un transfert local.
      if (name.contains('vmware') || name.contains('virtualbox') || name.contains('vethernet') || name.startsWith('docker') || name.startsWith('br-') || name.startsWith('veth')) {
        continue;
      }
      for (final a in ni.addresses) {
        if (isPrivateIPv4(a.address)) out.add(LocalAddress(ni.name, a));
      }
    }
    // Wi-Fi / Ethernet classiques (192.168.x) en premier.
    out.sort((a, b) => _rank(a.address.address).compareTo(_rank(b.address.address)));
    return out;
  } catch (_) {
    return const [];
  }
}

int _rank(String ip) {
  if (ip.startsWith('192.168.')) return 0;
  if (ip.startsWith('10.')) return 1;
  return 2;
}

bool isPrivateIPv4(String ip) {
  final p = ip.split('.').map(int.tryParse).toList();
  if (p.length != 4 || p.any((e) => e == null)) return false;
  final a = p[0]!, b = p[1]!;
  return a == 10 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168) || (a == 169 && b == 254);
}

bool isValidIPv4(String ip) {
  final p = ip.trim().split('.');
  if (p.length != 4) return false;
  return p.every((e) {
    final v = int.tryParse(e);
    return v != null && v >= 0 && v <= 255 && e.isNotEmpty;
  });
}

/// Adresse de broadcast en supposant un masque /24 (cas de quasiment tous les
/// box et points d'accès). Dart n'expose pas le masque réseau.
String broadcastFor(String ip) {
  final p = ip.split('.');
  return '${p[0]}.${p[1]}.${p[2]}.255';
}

/// Même sous-réseau /24 qu'une de nos adresses ?
bool sameSubnet(String remote, List<LocalAddress> locals) {
  if (!isValidIPv4(remote)) return true; // nom d'hôte : on ne peut pas juger
  final r = remote.split('.');
  for (final l in locals) {
    final p = l.address.address.split('.');
    if (p[0] == r[0] && p[1] == r[1] && p[2] == r[2]) return true;
    // Réseaux en /16 (10.x d'entreprise, 172.16-31.x)
    if (p[0] == '10' && r[0] == '10' && p[1] == r[1]) return true;
    if (p[0] == '172' && r[0] == '172' && p[1] == r[1]) return true;
  }
  return false;
}
