// Tests d'intégration du moteur : deux instances réelles de Transferys qui
// communiquent en HTTPS sur la machine (appairage, envois, reprise, erreurs).
//
// Lancer : flutter test test/engine_test.dart
// Test 5 Go : TRANSFERYS_BIG=1 flutter test test/engine_test.dart --name "5 Go"
import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:transferys/core/models.dart';
import 'package:transferys/core/settings.dart';
import 'package:transferys/engine.dart';
import 'package:transferys/platform/platform_hooks.dart';
import 'package:transferys/transfer/file_source.dart';
import 'package:transferys/transfer/job.dart';
import 'package:transferys/transfer/server.dart';

class TestHooks extends DefaultPlatformHooks {
  int? fakeFree;
  bool unknownFree = false;
  @override
  Future<int?> freeSpace(String dir) async {
    if (unknownFree) return null;
    return fakeFree ?? super.freeSpace(dir);
  }
}

class Node {
  Node(this.name, this.root);
  final String name;
  final Directory root;
  late TransferysEngine engine;
  final hooks = TestHooks();
  final codes = StreamController<PairingPrompt>.broadcast();
  bool accept = true;
  PairingPrompt? lastPrompt;
  int incomingCount = 0;

  String get recvDir => p.join(root.path, 'recu');

  Future<void> boot({int port = 0}) async {
    engine = TransferysEngine(
      dataDir: p.join(root.path, 'data'),
      platform: DevicePlatform.linux,
      hooks: hooks,
      enableDiscovery: false,
      defaults: Settings(deviceName: name, receiveDir: recvDir, port: port),
    );
    await engine.init();
    engine.settings.port = port;
    engine.onPairingPrompt = (pp) {
      lastPrompt = pp;
      codes.add(pp);
    };
    engine.onIncoming = (r) async {
      incomingCount++;
      return accept;
    };
    final err = await engine.start();
    expect(err, isNull);
  }

  Future<void> shutdown() => engine.stop();
}

Future<Directory> tmp(String n) => Directory.systemTemp.createTemp('transferys_$n');

Future<File> makeFile(String path, int size, {int seed = 1}) async {
  final f = File(path);
  await f.parent.create(recursive: true);
  final r = Random(seed);
  final raf = await f.open(mode: FileMode.write);
  const block = 1 << 20;
  final buf = List<int>.generate(block, (_) => r.nextInt(256));
  var left = size;
  var k = 0;
  while (left > 0) {
    final n = left < block ? left : block;
    // varie le contenu pour que chaque Mo soit différent
    buf[0] = k & 0xff;
    buf[1] = (k >> 8) & 0xff;
    await raf.writeFrom(buf, 0, n);
    left -= n;
    k++;
  }
  await raf.close();
  return f;
}

Future<String> sha(String path) async => (await sha256.bind(File(path).openRead()).first).toString();

Future<void> pairNodes(Node a, Node b) async {
  final peer = await a.engine.probe('127.0.0.1', b.engine.port);
  final dev = await a.engine.pair(peer, (name, err) async {
    return b.lastPrompt!.code;
  }).timeout(const Duration(seconds: 20));
  expect(dev.name, b.name);
  expect(b.engine.trust.get(a.engine.identity.id), isNotNull);
}

Future<TransferJob> waitJob(TransferJob j, {Duration timeout = const Duration(minutes: 5)}) async {
  final end = DateTime.now().add(timeout);
  while (j.isActive) {
    if (DateTime.now().isAfter(end)) throw TimeoutException('job toujours actif: ${j.status} ${j.error}');
    await Future.delayed(const Duration(milliseconds: 50));
  }
  return j;
}

/// Proxy TCP qu'on peut couper pour simuler une perte de Wi-Fi.
class CuttableProxy {
  CuttableProxy(this.targetPort);
  final int targetPort;
  ServerSocket? _server;
  int port = 0;
  final _sockets = <Socket>[];
  int bytes = 0;

  Future<void> start({int? onPort}) async {
    _server = await ServerSocket.bind(InternetAddress.loopbackIPv4, onPort ?? port, shared: true);
    port = _server!.port;
    _server!.listen((client) async {
      try {
        final up = await Socket.connect('127.0.0.1', targetPort);
        _sockets..add(client)..add(up);
        client.listen((d) {
          bytes += d.length;
          up.add(d);
        }, onDone: () => up.destroy(), onError: (_) => up.destroy());
        up.listen(client.add, onDone: () => client.destroy(), onError: (_) => client.destroy());
      } catch (_) {
        client.destroy();
      }
    });
  }

  Future<void> cut() async {
    await _server?.close();
    for (final s in _sockets) {
      s.destroy();
    }
    _sockets.clear();
  }
}

void main() {
  late Node a, b;

  setUp(() async {
    a = Node('PC Bureau', await tmp('a'));
    b = Node('Tel Quentin', await tmp('b'));
    await a.boot();
    await b.boot();
  });

  tearDown(() async {
    await a.shutdown();
    await b.shutdown();
    // Windows refuse de supprimer un fichier encore en cours d'écriture
    // (historique écrit juste après la fin) : on réessaie un peu plus tard.
    for (final d in [a.root, b.root]) {
      for (var i = 0; i < 20; i++) {
        try {
          if (d.existsSync()) await d.delete(recursive: true);
          break;
        } on FileSystemException {
          await Future.delayed(const Duration(milliseconds: 250));
        }
      }
    }
  });

  test('appairage par code + mauvais code', () async {
    final peer = await a.engine.probe('127.0.0.1', b.engine.port);
    var asked = 0;
    final dev = await a.engine.pair(peer, (name, err) async {
      asked++;
      final code = b.lastPrompt!.code;
      if (asked == 1) {
        expect(err, isNull);
        return code == '000000' ? '111111' : '000000';
      }
      expect(err, contains('Code incorrect'));
      return code;
    });
    expect(asked, 2);
    expect(dev.fingerprint, b.engine.identity.fingerprint);
    expect(b.engine.trust.get(a.engine.identity.id)!.fingerprint, a.engine.identity.fingerprint);
  });

  test('envoi refusé sans appairage', () async {
    expect(() => a.engine.send('inconnu', []), throwsA(anything));
  });

  test('fichiers + dossier avec sous-dossiers, SHA-256 identiques', () async {
    await pairNodes(a, b);
    final src = p.join(a.root.path, 'src');
    await makeFile(p.join(src, 'video.mp4'), 37 * 1024 * 1024 + 123, seed: 2);
    await makeFile(p.join(src, 'vide.txt'), 0);
    await makeFile(p.join(src, 'Vacances', 'IMG_1.jpg'), 2 * 1024 * 1024, seed: 3);
    await makeFile(p.join(src, 'Vacances', 'Plage', 'IMG_2.jpg'), 500 * 1024, seed: 4);
    final sources = await expandLocalPaths([p.join(src, 'video.mp4'), p.join(src, 'vide.txt'), p.join(src, 'Vacances')]);
    expect(sources.map((s) => s.relPath), containsAll(['Vacances/IMG_1.jpg', 'Vacances/Plage/IMG_2.jpg']));
    final job = await waitJob(a.engine.send(b.engine.identity.id, sources));
    expect(job.status, TransferStatus.done, reason: job.error);
    for (final rel in ['video.mp4', 'vide.txt', 'Vacances/IMG_1.jpg', 'Vacances/Plage/IMG_2.jpg']) {
      expect(await sha(p.join(b.recvDir, rel)), await sha(p.join(src, rel)), reason: rel);
    }
    expect(Directory(p.join(b.recvDir, '.transferys-partial')).existsSync(), isFalse);
    expect(b.incomingCount, 1);
    expect(a.engine.history.entries.first.status, TransferStatus.done);
    // L'historique côté réception est écrit quand l'émetteur signale la fin.
    await Future.delayed(const Duration(milliseconds: 300));
    expect(b.engine.history.entries.first.files.length, 4);
  });

  test('sens inverse (B → A) après appairage dans un seul sens', () async {
    await pairNodes(a, b);
    // B connaît A grâce à l'appairage ; il le joint à l'adresse de la requête.
    b.engine.trust.get(a.engine.identity.id)!
      ..lastAddress = '127.0.0.1'
      ..lastPort = a.engine.port;
    final f = await makeFile(p.join(b.root.path, 'photo.jpg'), 3 * 1024 * 1024, seed: 9);
    final job = await waitJob(b.engine.send(a.engine.identity.id, [LocalFileSource(f.path)]));
    expect(job.status, TransferStatus.done, reason: job.error);
    expect(await sha(p.join(a.recvDir, 'photo.jpg')), await sha(f.path));
  });

  test('500 petits fichiers d\'un coup', () async {
    await pairNodes(a, b);
    final dir = p.join(a.root.path, 'petits');
    for (var i = 0; i < 500; i++) {
      await makeFile(p.join(dir, 'f_$i.txt'), 1000 + i * 37, seed: i);
    }
    final sw = Stopwatch()..start();
    final job = await waitJob(a.engine.send(b.engine.identity.id, await expandLocalPaths([dir])));
    expect(job.status, TransferStatus.done, reason: job.error);
    expect(Directory(p.join(b.recvDir, 'petits')).listSync().length, 500);
    expect(await sha(p.join(b.recvDir, 'petits', 'f_499.txt')), await sha(p.join(dir, 'f_499.txt')));
    // ignore: avoid_print
    print('500 fichiers en ${sw.elapsedMilliseconds} ms');
  });

  test('coupure réseau en plein transfert puis reprise automatique', () async {
    await pairNodes(a, b);
    final proxy = CuttableProxy(b.engine.port);
    await proxy.start();
    // A passe par le proxy pour joindre B.
    a.engine.discovery.forget(b.engine.identity.id);
    a.engine.trust.get(b.engine.identity.id)!
      ..lastAddress = '127.0.0.1'
      ..lastPort = proxy.port;
    final f = await makeFile(p.join(a.root.path, 'gros.bin'), 300 * 1024 * 1024, seed: 5);
    final job = a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]);
    while (job.transferredBytes < 60 * 1024 * 1024) {
      await Future.delayed(const Duration(milliseconds: 20));
    }
    await proxy.cut(); // « le Wi-Fi tombe »
    final cutAt = job.transferredBytes;
    await Future.delayed(const Duration(seconds: 1));
    expect(job.status, anyOf(TransferStatus.reconnecting, TransferStatus.running));
    await Future.delayed(const Duration(seconds: 3));
    await proxy.start(onPort: proxy.port); // « le Wi-Fi revient »
    await waitJob(job);
    expect(job.status, TransferStatus.done, reason: job.error);
    expect(await sha(p.join(b.recvDir, 'gros.bin')), await sha(f.path));
    // On n'a pas tout renvoyé depuis le début.
    // ignore: avoid_print
    print('coupé à ${cutAt >> 20} Mo, octets via proxy : ${proxy.bytes >> 20} Mo');
    expect(proxy.bytes, lessThan(300 * 1024 * 1024 * 1.2));
  }, timeout: const Timeout(Duration(minutes: 5)));

  test('redémarrage du destinataire : reprise depuis le fichier partiel', () async {
    await pairNodes(a, b);
    final f = await makeFile(p.join(a.root.path, 'film.mkv'), 200 * 1024 * 1024, seed: 6);
    a.engine.trust.get(b.engine.identity.id)!.lastPort = b.engine.port;
    final port = b.engine.port;
    final job = a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]);
    while (job.transferredBytes < 80 * 1024 * 1024) {
      await Future.delayed(const Duration(milliseconds: 20));
    }
    await b.shutdown(); // appli fermée / téléphone redémarré
    await Future.delayed(const Duration(seconds: 2));
    expect(job.isActive, isTrue, reason: '${job.status} ${job.error}');
    await b.boot(port: port); // même dossier de données, même port
    await waitJob(job);
    expect(job.status, TransferStatus.done, reason: job.error);
    expect(await sha(p.join(b.recvDir, 'film.mkv')), await sha(f.path));
    expect(b.incomingCount, 2); // la reprise est redemandée à l'utilisateur
  }, timeout: const Timeout(Duration(minutes: 5)));

  test('espace disque insuffisant (contrôle avant envoi)', () async {
    await pairNodes(a, b);
    b.hooks.fakeFree = 10 * 1024 * 1024;
    final f = await makeFile(p.join(a.root.path, 'trop_gros.bin'), 80 * 1024 * 1024);
    final job = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]));
    expect(job.status, TransferStatus.failed);
    expect(job.error, contains('Espace disque insuffisant'));
  });

  test('disque plein pendant l\'écriture (tmpfs de 20 Mo)', () async {
    if (Platform.environment['USER'] != 'root' && Platform.environment['HOME'] != '/root') {
      markTestSkipped('nécessite root pour monter un tmpfs');
      return;
    }
    final mnt = Directory(p.join(b.root.path, 'petit_disque'))..createSync();
    final r = await Process.run('mount', ['-t', 'tmpfs', '-o', 'size=20m', 'tmpfs', mnt.path]);
    if (r.exitCode != 0) {
      markTestSkipped('mount impossible: ${r.stderr}');
      return;
    }
    try {
      await pairNodes(a, b);
      b.engine.settings.receiveDir = mnt.path;
      b.hooks.unknownFree = true; // on contourne le contrôle préalable
      final f = await makeFile(p.join(a.root.path, 'gros.bin'), 60 * 1024 * 1024);
      final job = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]));
      expect(job.status, TransferStatus.failed);
      expect(job.error, contains('Espace disque insuffisant'));
    } finally {
      await Process.run('umount', [mnt.path]);
    }
  });

  test('refus par le destinataire', () async {
    await pairNodes(a, b);
    b.accept = false;
    final f = await makeFile(p.join(a.root.path, 'x.txt'), 10);
    final job = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]));
    expect(job.status, TransferStatus.rejected);
    expect(job.error, contains('refusé'));
  });

  test('pause longue (veille) puis reprise, et annulation', () async {
    await pairNodes(a, b);
    final f = await makeFile(p.join(a.root.path, 'pause.bin'), 120 * 1024 * 1024, seed: 7);
    final job = a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]);
    while (job.transferredBytes < 20 * 1024 * 1024) {
      await Future.delayed(const Duration(milliseconds: 10));
    }
    job.pause();
    await Future.delayed(const Duration(milliseconds: 500));
    final frozen = job.transferredBytes;
    await Future.delayed(const Duration(seconds: 70)); // > délais d'inactivité HTTP
    expect(job.transferredBytes, frozen);
    expect(job.status, TransferStatus.paused);
    job.resume();
    await waitJob(job);
    expect(job.status, TransferStatus.done, reason: job.error);
    expect(await sha(p.join(b.recvDir, 'pause.bin')), await sha(f.path));

    // Annulation : les morceaux sont supprimés chez le destinataire.
    final g = await makeFile(p.join(a.root.path, 'annule.bin'), 120 * 1024 * 1024, seed: 8);
    final job2 = a.engine.send(b.engine.identity.id, [LocalFileSource(g.path)]);
    while (job2.transferredBytes < 20 * 1024 * 1024) {
      await Future.delayed(const Duration(milliseconds: 10));
    }
    job2.cancel();
    await waitJob(job2);
    expect(job2.status, TransferStatus.cancelled);
    await Future.delayed(const Duration(seconds: 1));
    expect(File(p.join(b.recvDir, 'annule.bin')).existsSync(), isFalse);
    final partial = Directory(p.join(b.recvDir, '.transferys-partial'));
    expect(!partial.existsSync() || partial.listSync().isEmpty, isTrue);
  }, timeout: const Timeout(Duration(minutes: 3)));

  test('doublons : renommer, ignorer, remplacer', () async {
    await pairNodes(a, b);
    final f = await makeFile(p.join(a.root.path, 'doc.pdf'), 1000, seed: 1);
    Future<void> sendOnce() async {
      final j = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]));
      expect(j.status, TransferStatus.done, reason: j.error);
    }

    await sendOnce();
    await sendOnce(); // renommer (défaut)
    expect(File(p.join(b.recvDir, 'doc (1).pdf')).existsSync(), isTrue);
    b.engine.settings.duplicateMode = DuplicateMode.skip;
    final j = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]));
    expect(j.files.first.status, TransferStatus.skipped);
    expect(File(p.join(b.recvDir, 'doc (2).pdf')).existsSync(), isFalse);
    b.engine.settings.duplicateMode = DuplicateMode.replace;
    await File(p.join(b.recvDir, 'doc.pdf')).writeAsString('ancien');
    await sendOnce();
    expect(await sha(p.join(b.recvDir, 'doc.pdf')), await sha(f.path));
  });

  test('chemins malveillants neutralisés', () async {
    await pairNodes(a, b);
    final f = await makeFile(p.join(a.root.path, 'x.bin'), 100);
    final job = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(f.path, relPath: '../../etc/CON:evil?.txt')]));
    expect(job.status, TransferStatus.done, reason: job.error);
    expect(File(p.join(b.recvDir, 'etc', 'CON_evil_.txt')).existsSync(), isTrue);
  });

  test('débit', () async {
    await pairNodes(a, b);
    final f = await makeFile(p.join(a.root.path, 'debit.bin'), 200 * 1024 * 1024, seed: 11);
    final sw = Stopwatch()..start();
    final job = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(f.path)]));
    expect(job.status, TransferStatus.done, reason: job.error);
    // ignore: avoid_print
    print('200 Mo en ${sw.elapsedMilliseconds} ms = ${(200000 / sw.elapsedMilliseconds).toStringAsFixed(1)} Mo/s');
  }, timeout: const Timeout(Duration(minutes: 5)));

  test('5 Go', () async {
    if (Platform.environment['TRANSFERYS_BIG'] != '1') {
      markTestSkipped('TRANSFERYS_BIG=1 pour lancer le test 5 Go');
      return;
    }
    await pairNodes(a, b);
    final path = p.join(a.root.path, 'video_5go.mp4');
    // fichier creux rempli par blocs aléatoires (rapide à générer)
    final dd = await Process.run('sh', ['-c', 'head -c 5368709120 /dev/urandom > "$path"']);
    expect(dd.exitCode, 0);
    final sw = Stopwatch()..start();
    final job = await waitJob(a.engine.send(b.engine.identity.id, [LocalFileSource(path)]), timeout: const Duration(minutes: 30));
    final secs = sw.elapsedMilliseconds / 1000;
    expect(job.status, TransferStatus.done, reason: job.error);
    final recv = p.join(b.recvDir, 'video_5go.mp4');
    expect(File(recv).lengthSync(), 5368709120);
    expect(await sha(recv), await sha(path));
    // ignore: avoid_print
    print('5 Go transférés en ${secs.toStringAsFixed(1)} s (${(5120 / secs).toStringAsFixed(0)} Mo/s, TLS + SHA-256 des deux côtés)');
  }, timeout: const Timeout(Duration(minutes: 40)));
}
