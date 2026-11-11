// Client UPnP IGD minimal : demande à la box (Freebox, Livebox…) d'ouvrir
// un port vers ce PC et récupère l'adresse Internet de la box.
// Tout se passe entre le PC et la box, sur le réseau local : aucun site
// extérieur n'est contacté.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

class UpnpResult {
  UpnpResult({this.externalIp, this.mapped = false, this.error, this.gatewayName});
  final String? externalIp;
  final bool mapped;
  final String? error;
  final String? gatewayName;
}

class _Service {
  _Service(this.type, this.controlUrl);
  final String type;
  final Uri controlUrl;
}

class UpnpClient {
  UpnpClient({this.ssdpAddress = '239.255.255.250', this.ssdpPort = 1900, this.timeout = const Duration(seconds: 3), this.location});
  final String ssdpAddress;

  /// Adresse de description connue (tests) : saute la recherche SSDP.
  final Uri? location;
  final int ssdpPort;
  final Duration timeout;

  _Service? _service;
  String? gatewayName;

  static const _searchTargets = [
    'urn:schemas-upnp-org:device:InternetGatewayDevice:2',
    'urn:schemas-upnp-org:device:InternetGatewayDevice:1',
    'urn:schemas-upnp-org:service:WANIPConnection:2',
    'urn:schemas-upnp-org:service:WANIPConnection:1',
    'urn:schemas-upnp-org:service:WANPPPConnection:1',
  ];

  /// Recherche la box sur le réseau (SSDP) et sa description.
  Future<bool> discover() async {
    if (location != null) {
      _service = await _fetchService(location!);
      return _service != null;
    }
    final locations = <String>{};
    RawDatagramSocket? s;
    try {
      s = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
      final sock = s;
      sock.listen((ev) {
        if (ev != RawSocketEvent.read) return;
        Datagram? d;
        while ((d = sock.receive()) != null) {
          final txt = utf8.decode(d!.data, allowMalformed: true);
          for (final line in txt.split('\r\n')) {
            final i = line.indexOf(':');
            if (i > 0 && line.substring(0, i).trim().toLowerCase() == 'location') {
              locations.add(line.substring(i + 1).trim());
            }
          }
        }
      });
      for (var round = 0; round < 2; round++) {
        for (final st in _searchTargets) {
          final msg = 'M-SEARCH * HTTP/1.1\r\nHOST: $ssdpAddress:$ssdpPort\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: $st\r\n\r\n';
          sock.send(utf8.encode(msg), InternetAddress(ssdpAddress), ssdpPort);
        }
        await Future.delayed(const Duration(milliseconds: 900));
        if (locations.isNotEmpty) break;
      }
      await Future.delayed(const Duration(milliseconds: 400));
    } catch (_) {
      return false;
    } finally {
      s?.close();
    }
    for (final loc in locations) {
      final svc = await _fetchService(Uri.parse(loc));
      if (svc != null) {
        _service = svc;
        return true;
      }
    }
    return false;
  }

  Future<_Service?> _fetchService(Uri location) async {
    final c = HttpClient()..connectionTimeout = timeout;
    c.findProxy = (_) => 'DIRECT';
    try {
      final req = await c.getUrl(location).timeout(timeout);
      final res = await req.close().timeout(timeout);
      final xml = await utf8.decodeStream(res).timeout(timeout);
      gatewayName = RegExp(r'<friendlyName>([^<]*)</friendlyName>').firstMatch(xml)?.group(1);
      final base = RegExp(r'<URLBase>([^<]*)</URLBase>').firstMatch(xml)?.group(1);
      final baseUri = base != null && base.isNotEmpty ? Uri.parse(base) : location;
      for (final m in RegExp(r'<service>(.*?)</service>', dotAll: true).allMatches(xml)) {
        final block = m.group(1)!;
        final type = RegExp(r'<serviceType>([^<]*)</serviceType>').firstMatch(block)?.group(1)?.trim() ?? '';
        if (!type.contains('WANIPConnection') && !type.contains('WANPPPConnection')) continue;
        final ctrl = RegExp(r'<controlURL>([^<]*)</controlURL>').firstMatch(block)?.group(1)?.trim();
        if (ctrl == null) continue;
        return _Service(type, baseUri.resolve(ctrl));
      }
    } catch (_) {
    } finally {
      c.close(force: true);
    }
    return null;
  }

  Future<Map<String, String>> _soap(String action, Map<String, String> args) async {
    final svc = _service!;
    final body = StringBuffer()
      ..write('<?xml version="1.0"?>')
      ..write('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">')
      ..write('<s:Body><u:$action xmlns:u="${svc.type}">');
    args.forEach((k, v) => body.write('<$k>${const HtmlEscape().convert(v)}</$k>'));
    body.write('</u:$action></s:Body></s:Envelope>');
    final c = HttpClient()..connectionTimeout = timeout;
    c.findProxy = (_) => 'DIRECT';
    try {
      final req = await c.postUrl(svc.controlUrl).timeout(timeout);
      final bytes = utf8.encode(body.toString());
      req.headers
        ..set('Content-Type', 'text/xml; charset="utf-8"')
        ..set('SOAPAction', '"${svc.type}#$action"');
      req.contentLength = bytes.length;
      req.add(bytes);
      final res = await req.close().timeout(timeout);
      final xml = await utf8.decodeStream(res).timeout(timeout);
      if (res.statusCode != 200) {
        final code = RegExp(r'<errorCode>(\d+)</errorCode>').firstMatch(xml)?.group(1);
        final desc = RegExp(r'<errorDescription>([^<]*)</errorDescription>').firstMatch(xml)?.group(1);
        throw HttpException('UPnP $action refusé (${code ?? res.statusCode} ${desc ?? ''})');
      }
      final out = <String, String>{};
      for (final m in RegExp(r'<(New\w+)>([^<]*)</\1>').allMatches(xml)) {
        out[m.group(1)!] = m.group(2)!;
      }
      return out;
    } finally {
      c.close(force: true);
    }
  }

  /// Ouvre [port] (TCP) vers [localIp] et renvoie l'adresse Internet de la box.
  Future<UpnpResult> openPort({required int port, required String localIp, Duration lease = const Duration(hours: 2)}) async {
    if (_service == null && !await discover()) {
      return UpnpResult(
          error: 'Box introuvable en UPnP. Sur Freebox : Freebox OS > Paramètres de la Freebox > Mode avancé > UPnP IGD > Activer.');
    }
    String? ext;
    try {
      ext = (await _soap('GetExternalIPAddress', {}))['NewExternalIPAddress'];
    } catch (_) {}
    Future<void> add(int leaseSec) => _soap('AddPortMapping', {
          'NewRemoteHost': '',
          'NewExternalPort': '$port',
          'NewProtocol': 'TCP',
          'NewInternalPort': '$port',
          'NewInternalClient': localIp,
          'NewEnabled': '1',
          'NewPortMappingDescription': 'Transferys',
          'NewLeaseDuration': '$leaseSec',
        });
    try {
      try {
        await add(lease.inSeconds);
      } catch (_) {
        // Certaines box n'acceptent que les baux permanents (0).
        await add(0);
      }
      return UpnpResult(externalIp: ext, mapped: true, gatewayName: gatewayName);
    } catch (e) {
      return UpnpResult(externalIp: ext, mapped: false, error: '$e', gatewayName: gatewayName);
    }
  }

  Future<void> closePort(int port) async {
    if (_service == null) return;
    try {
      await _soap('DeletePortMapping', {'NewRemoteHost': '', 'NewExternalPort': '$port', 'NewProtocol': 'TCP'});
    } catch (_) {}
  }
}

/// Adresse IPv4 publique « utilisable » (pas privée ni CGNAT 100.64/10).
bool isPublicIPv4(String? ip) {
  if (ip == null) return false;
  final p = ip.split('.').map(int.tryParse).toList();
  if (p.length != 4 || p.any((e) => e == null)) return false;
  final a = p[0]!, b = p[1]!;
  if (a == 10 || a == 127 || a == 0 || (a == 172 && b >= 16 && b <= 31) || (a == 192 && b == 168)) return false;
  if (a == 100 && b >= 64 && b <= 127) return false; // CGNAT
  if (a == 169 && b == 254) return false;
  return true;
}

/// Adresses IPv6 globales de cette machine (joignables depuis Internet si la
/// box ne les filtre pas). Exclut lien-local (fe80::/10) et ULA (fc00::/7).
Future<List<String>> globalIPv6Addresses() async {
  try {
    final list = await NetworkInterface.list(type: InternetAddressType.IPv6, includeLoopback: false);
    final out = <String>[];
    for (final ni in list) {
      for (final a in ni.addresses) {
        final s = a.address.toLowerCase();
        if (s.startsWith('fe8') || s.startsWith('fe9') || s.startsWith('fea') || s.startsWith('feb')) continue;
        if (s.startsWith('fc') || s.startsWith('fd') || s == '::1') continue;
        if (!(s.startsWith('2') || s.startsWith('3'))) continue;
        out.add(a.address.split('%').first);
      }
    }
    return out;
  } catch (_) {
    return const [];
  }
}
