// Tests de sécurité : un appareil inconnu du réseau ne doit pas pouvoir
// devenir « de confiance » sans une action de l'utilisateur.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:transferys/core/models.dart';
import 'package:transferys/core/settings.dart';
import 'package:transferys/engine.dart';
import 'package:transferys/security/identity.dart';
import 'package:transferys/security/pairing.dart';
import 'package:transferys/transfer/client.dart';

void main() {
  late Directory root;
  late TransferysEngine victim;
  String? shownPairId;

  setUp(() async {
    root = await Directory.systemTemp.createTemp('tr_sec');
    victim = TransferysEngine(
      dataDir: p.join(root.path, 'data'),
      platform: DevicePlatform.linux,
      enableDiscovery: false,
      defaults: Settings(deviceName: 'PC Bureau', receiveDir: p.join(root.path, 'recu'), port: 0),
    );
    await victim.init();
    victim.settings.port = 0;
    victim.onPairingPrompt = (pp) => shownPairId = pp.pairId; // l'utilisateur ne touche à rien
    await victim.start();
  });

  tearDown(() async {
    await victim.stop();
    await root.delete(recursive: true);
  });

  test('un attaquant qui calcule lui-même le code ne peut pas s\'appairer seul', () async {
    final evil = DeviceIdentity.generate();
    final c = PeerClient(host: '127.0.0.1', port: victim.port, myId: evil.id);
    final hello = await c.json('POST', '/pair/hello',
        body: {'id': evil.id, 'name': 'Intrus', 'platform': 'android', 'fingerprint': evil.fingerprint, 'port': 1});
    final nonceA = randomToken(16);
    final r2 = await c.json('POST', '/pair/nonce', body: {'pairId': hello.body['pairId'], 'nonceA': nonceA});
    // L'attaquant connaît tous les ingrédients du code : il le calcule sans voir l'écran.
    final code = pairingCode(
        fingerprintA: evil.fingerprint, fingerprintB: c.seenFingerprint!, nonceA: nonceA, nonceB: r2.body['nonceB'] as String);
    final r3 = await c.json('POST', '/pair/confirm',
        body: {'pairId': hello.body['pairId'], 'code': code, 'secret': randomToken(32)}, timeout: const Duration(seconds: 8))
        .catchError((_) => ApiResponse(0, {}));
    c.close();
    expect(r3.ok, isFalse, reason: 'appairage accepté sans action de l\'utilisateur');
    expect(victim.trust.get(evil.id), isNull);
    expect(shownPairId, isNotNull);
  });

  test('appairage normal : code saisi + clic Autoriser', () async {
    final other = TransferysEngine(
      dataDir: p.join(root.path, 'data2'),
      platform: DevicePlatform.android,
      enableDiscovery: false,
      defaults: Settings(deviceName: 'Tel', receiveDir: p.join(root.path, 'recu2'), port: 0),
    );
    await other.init();
    other.settings.port = 0;
    await other.start();
    String? code;
    victim.onPairingPrompt = (pp) {
      code = pp.code;
      Future.delayed(const Duration(milliseconds: 300), () => victim.approvePairing(pp.pairId));
    };
    final peer = await other.probe('127.0.0.1', victim.port);
    final dev = await other.pair(peer, (n, e) async => code);
    expect(dev.name, 'PC Bureau');
    expect(victim.trust.get(other.identity.id), isNotNull);
    await other.stop();
  });

  test('/info ne révèle rien à un inconnu venant d\'Internet', () {
    final full = victim.infoJson();
    expect(full['name'], 'PC Bureau');
    expect(victim.publicInfoJson().keys, ['app']);
  });
}
