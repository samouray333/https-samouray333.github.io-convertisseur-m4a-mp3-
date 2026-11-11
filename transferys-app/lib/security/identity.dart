// Identité cryptographique de l'appareil : certificat TLS auto-signé (ECDSA
// P-256) généré localement au premier lancement, jamais envoyé ailleurs que
// sur le réseau local.
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:basic_utils/basic_utils.dart';
import 'package:crypto/crypto.dart';
import 'package:uuid/uuid.dart';

import '../core/storage.dart';

class DeviceIdentity {
  DeviceIdentity({required this.id, required this.certPem, required this.keyPem})
      : fingerprint = fingerprintOfPem(certPem);

  /// Identifiant stable de l'appareil (UUID).
  final String id;
  final String certPem;
  final String keyPem;

  /// SHA-256 (hexadécimal) du certificat DER : ce que les autres appareils épinglent.
  final String fingerprint;

  /// Contexte TLS côté serveur.
  SecurityContext serverContext() {
    final ctx = SecurityContext(withTrustedRoots: false);
    ctx.useCertificateChainBytes(utf8.encode(certPem));
    ctx.usePrivateKeyBytes(utf8.encode(keyPem));
    return ctx;
  }

  /// Empreinte courte lisible, ex. « 3F9A-1C2B ».
  String get shortFingerprint => shortFp(fingerprint);

  static String shortFp(String fp) =>
      fp.length < 8 ? fp : '${fp.substring(0, 4)}-${fp.substring(4, 8)}'.toUpperCase();

  static String fingerprintOfPem(String pem) =>
      sha256.convert(CryptoUtils.getBytesFromPEMString(pem)).toString();

  static String fingerprintOfDer(List<int> der) => sha256.convert(der).toString();

  /// Charge l'identité depuis [dataDir], ou la crée au premier lancement.
  static Future<DeviceIdentity> loadOrCreate(String dataDir) async {
    final file = JsonFile(joinData(dataDir, 'identity.json'));
    final j = await file.read();
    if (j is Map && j['id'] is String && j['cert'] is String && j['key'] is String) {
      try {
        final ident = DeviceIdentity(id: j['id'] as String, certPem: j['cert'] as String, keyPem: j['key'] as String);
        ident.serverContext(); // valide les PEM
        return ident;
      } catch (_) {
        // identité illisible : on en régénère une
      }
    }
    final ident = generate();
    await file.write({'id': ident.id, 'cert': ident.certPem, 'key': ident.keyPem});
    return ident;
  }

  static DeviceIdentity generate() {
    final id = const Uuid().v4();
    final kp = CryptoUtils.generateEcKeyPair(curve: 'prime256v1');
    final priv = kp.privateKey as ECPrivateKey;
    final pub = kp.publicKey as ECPublicKey;
    final csr = X509Utils.generateEccCsrPem({'CN': 'Transferys $id', 'O': 'Transferys'}, priv, pub);
    // 20 ans : le certificat ne sert qu'à l'épinglage, pas à une autorité.
    final cert = X509Utils.generateSelfSignedCertificate(priv, csr, 7300,
        serialNumber: BigInt.from(Random.secure().nextInt(1 << 31)).toString());
    return DeviceIdentity(id: id, certPem: cert, keyPem: CryptoUtils.encodeEcPrivateKeyToPem(priv));
  }
}
