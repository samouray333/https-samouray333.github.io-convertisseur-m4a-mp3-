// Constantes et utilitaires du protocole HTTPS de Transferys (v1).
//
// Routes (toutes en HTTPS, certificat épinglé) :
//   GET  /api/v1/info                              identité de l'appareil
//   POST /api/v1/pair/hello                        appairage étape 1 (engagement)
//   POST /api/v1/pair/nonce                        appairage étape 2 (révélation)
//   POST /api/v1/pair/confirm                      appairage étape 3 (secret)
//   POST /api/v1/session                           demande d'envoi (liste des fichiers)
//   PUT  /api/v1/session/<sid>/file/<fid>?offset=N un morceau (chunk) de fichier
//   GET  /api/v1/session/<sid>/file/<fid>          octets déjà reçus (reprise)
//   POST /api/v1/session/<sid>/file/<fid>/finish   vérification SHA-256 + finalisation
//   POST /api/v1/session/<sid>/(pause|resume|cancel|done)
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

const int protocolVersion = 1;
const String apiPrefix = '/api/v1';

/// Taille d'un morceau envoyé par requête. 8 Mo : bon compromis entre débit,
/// réactivité de la pause et quantité de données à renvoyer après coupure.
const int chunkSize = 8 * 1024 * 1024;

/// Marge de sécurité exigée sur le disque en plus de la taille des fichiers.
const int diskMargin = 50 * 1024 * 1024;

const String headerDeviceId = 'x-transferys-id';
const String headerAuth = 'authorization';

Future<Map<String, dynamic>> readJsonBody(HttpRequest req, {int maxBytes = 16 * 1024 * 1024}) async {
  final b = BytesBuilder(copy: false);
  await for (final d in req) {
    b.add(d);
    if (b.length > maxBytes) throw const FormatException('Requête trop volumineuse');
  }
  if (b.isEmpty) return {};
  final j = jsonDecode(utf8.decode(b.takeBytes()));
  if (j is! Map) throw const FormatException('JSON attendu');
  return j.cast<String, dynamic>();
}

Future<void> sendJson(HttpRequest req, int status, Object body) async {
  final r = req.response;
  r.statusCode = status;
  r.headers.contentType = ContentType.json;
  r.write(jsonEncode(body));
  await r.close();
}

Future<Map<String, dynamic>> decodeJsonResponse(HttpClientResponse res) async {
  final s = await utf8.decodeStream(res);
  if (s.isEmpty) return {};
  final j = jsonDecode(s);
  return j is Map ? j.cast<String, dynamic>() : {'value': j};
}
