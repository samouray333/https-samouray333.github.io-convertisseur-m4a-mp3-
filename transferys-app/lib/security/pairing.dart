// Appairage par code à 6 chiffres.
//
// Principe (comparable à la « comparaison numérique » Bluetooth) :
//  1. L'émetteur (A) contacte le récepteur (B) en TLS et note l'empreinte du
//     certificat de B.
//  2. B tire un nonce nB et n'envoie d'abord que son engagement H(nB).
//  3. A envoie son nonce nA, puis B révèle nB (A vérifie l'engagement).
//  4. Les deux calculent code = H(empreinteA, empreinteB, nA, nB) mod 10^6.
//     B affiche le code, l'utilisateur le saisit sur A.
// Un intrus qui s'intercale présente un autre certificat : les deux codes
// diffèrent, et l'engagement l'empêche d'ajuster son nonce après coup.
// Le code n'est pas un secret : aucune attaque hors ligne n'est possible.
// Une fois le code vérifié, A envoie un secret aléatoire de 32 octets qui
// servira de jeton dans le canal TLS épinglé.
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

String randomToken([int bytes = 32]) {
  final r = Random.secure();
  return base64Url.encode(List<int>.generate(bytes, (_) => r.nextInt(256)));
}

String commitment(String nonce) => sha256.convert(utf8.encode('transferys-commit-v1|$nonce')).toString();

/// Code à 6 chiffres dérivé des deux empreintes et des deux nonces.
String pairingCode({
  required String fingerprintA,
  required String fingerprintB,
  required String nonceA,
  required String nonceB,
}) {
  final h = sha256.convert(utf8.encode('transferys-pair-v1|$fingerprintA|$fingerprintB|$nonceA|$nonceB'));
  var v = 0;
  for (var i = 0; i < 6; i++) {
    v = (v << 8) | h.bytes[i];
  }
  return (v % 1000000).toString().padLeft(6, '0');
}

/// Comparaison en temps constant.
bool constantTimeEquals(String a, String b) {
  if (a.length != b.length) return false;
  var r = 0;
  for (var i = 0; i < a.length; i++) {
    r |= a.codeUnitAt(i) ^ b.codeUnitAt(i);
  }
  return r == 0;
}
