// Client HTTPS vers un autre appareil Transferys, avec épinglage du
// certificat : on n'accepte QUE le certificat dont l'empreinte est connue
// (appareil de confiance ou QR code). Pendant le premier contact, l'empreinte
// vue est mémorisée puis vérifiée par le code d'appairage.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import '../core/errors.dart';
import '../security/identity.dart';
import 'protocol.dart';

class ApiResponse {
  ApiResponse(this.status, this.body);
  final int status;
  final Map<String, dynamic> body;
  bool get ok => status >= 200 && status < 300;
  String? get error => body['error'] as String?;
}

class PeerClient {
  PeerClient({
    required this.host,
    required this.port,
    required this.myId,
    this.expectedFingerprint,
    this.secret,
    this.connectTimeout = const Duration(seconds: 6),
  }) {
    _http = HttpClient(context: SecurityContext(withTrustedRoots: false))
      ..connectionTimeout = connectTimeout
      ..idleTimeout = const Duration(seconds: 20)
      ..maxConnectionsPerHost = 2
      ..findProxy = ((_) => 'DIRECT') // jamais de proxy : tout reste local
      ..badCertificateCallback = _checkCert;
  }

  String host;
  final int port;
  final String myId;

  /// Empreinte attendue (null = premier contact, on la mémorise).
  String? expectedFingerprint;
  String? secret;
  final Duration connectTimeout;
  late final HttpClient _http;

  /// Empreinte du certificat présenté par le serveur lors de la dernière connexion.
  String? seenFingerprint;
  bool _fingerprintMismatch = false;

  bool _checkCert(X509Certificate cert, String host, int port) {
    final fp = DeviceIdentity.fingerprintOfDer(cert.der);
    seenFingerprint = fp;
    if (expectedFingerprint == null) return true;
    final ok = fp == expectedFingerprint;
    _fingerprintMismatch = !ok;
    return ok;
  }

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri(scheme: 'https', host: host, port: port, path: '$apiPrefix$path', queryParameters: query);

  void _headers(HttpClientRequest r) {
    r.headers.set(headerDeviceId, myId);
    if (secret != null) r.headers.set(headerAuth, 'Bearer $secret');
  }

  Never _wrap(Object e) {
    if (_fingerprintMismatch) {
      throw TransferysException(ErrorCode.certificateChanged,
          'L\'identité de l\'appareil a changé (certificat différent). Par sécurité, retirez-le des appareils de confiance puis appairez-le à nouveau.');
    }
    if (e is TransferysException) throw e;
    throw e;
  }

  Future<ApiResponse> json(String method, String path,
      {Object? body, Map<String, String>? query, Duration timeout = const Duration(seconds: 20)}) async {
    try {
      final req = await _http.openUrl(method, _uri(path, query)).timeout(connectTimeout + const Duration(seconds: 4));
      _headers(req);
      if (body != null) {
        final bytes = utf8.encode(jsonEncode(body));
        req.headers.contentType = ContentType.json;
        req.contentLength = bytes.length;
        req.add(bytes);
      }
      final res = await req.close().timeout(timeout);
      final j = await decodeJsonResponse(res).timeout(timeout);
      return ApiResponse(res.statusCode, j);
    } catch (e) {
      _wrap(e);
    }
  }

  /// Envoie un morceau. [onSent] est appelé au fil de l'eau avec le nombre
  /// d'octets poussés, pour une barre de progression fluide.
  Future<ApiResponse> putChunk(String sid, String fid, int offset, Uint8List data,
      {void Function(int sent)? onSent, void Function(HttpClientRequest)? onRequest}) async {
    try {
      final req = await _http
          .openUrl('PUT', _uri('/session/$sid/file/$fid', {'offset': '$offset'}))
          .timeout(connectTimeout + const Duration(seconds: 4));
      onRequest?.call(req);
      _headers(req);
      req.headers.contentType = ContentType.binary;
      req.contentLength = data.length;
      req.bufferOutput = false;
      const piece = 256 * 1024;
      var sent = 0;
      for (var i = 0; i < data.length; i += piece) {
        final end = (i + piece < data.length) ? i + piece : data.length;
        req.add(Uint8List.sublistView(data, i, end));
        await req.flush().timeout(const Duration(seconds: 30));
        sent = end;
        onSent?.call(sent);
      }
      final res = await req.close().timeout(const Duration(seconds: 60));
      final j = await decodeJsonResponse(res).timeout(const Duration(seconds: 30));
      return ApiResponse(res.statusCode, j);
    } catch (e) {
      _wrap(e);
    }
  }

  void close({bool force = true}) => _http.close(force: force);
}
