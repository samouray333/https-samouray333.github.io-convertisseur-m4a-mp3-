// Tests de l'accès à distance : box UPnP simulée, explorateur de dossiers
// partagés, canal inverse (téléphone injoignable comme en 4G).
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:path/path.dart' as p;
import 'package:transferys/core/models.dart';
import 'package:transferys/core/settings.dart';
import 'package:transferys/engine.dart';
import 'package:transferys/network/upnp.dart';
import 'package:transferys/platform/platform_hooks.dart';
import 'package:transferys/transfer/file_source.dart';
import 'package:transferys/transfer/job.dart';
import 'package:transferys/transfer/server.dart';

class Node {
  Node(this.name, this.root, this.platform);
  final String name;
  final Directory root;
  final DevicePlatform platform;
  late TransferysEngine engine;
  PairingPrompt? lastPrompt;
  bool accept = true;
  int incoming = 0;
  String get recvDir => p.join(root.path, 'recu');

  Future<void> boot() async {
    engine = TransferysEngine(
      dataDir: p.join(root.path, 'data'),
      platform: platform,
      hooks: DefaultPlatformHooks(),
      enableDiscovery: false,
      defaults: Settings(deviceName: name, receiveDir: recvDir, port: 0),
    );
    await engine.init();
    engine.settings.port = 0;
    engine.onPairingPrompt = (pp) => lastPrompt = pp;
    engine.onIncoming = (r) async {
      incoming++;
      return accept;
    };
    await engine.start();
  }
}

Future<String> sha(String path) async => (await sha256.bind(File(path).openRead()).first).toString();

Future<File> mk(String path, int size, int seed) async {
  final f = File(path);
  await f.parent.create(recursive: true);
  await f.writeAsBytes(List<int>.generate(size, (i) => (i * 31 + seed * 7) & 0xff));
  return f;
}

Future<TransferJob> waitFor(TransferysEngine e, bool Function(TransferJob) where, {Duration timeout = const Duration(seconds: 60)}) async {
  final end = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(end)) {
    final j = e.jobs.where(where).firstOrNull;
    if (j != null && !j.isActive) return j;
    await Future.delayed(const Duration(milliseconds: 50));
  }
  throw TimeoutException('pas de transfert terminé');
}

void main() {
  test('UPnP : ouverture du port sur une box simulée', () async {
    final calls = <String>[];
    final srv = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    srv.listen((r) async {
      if (r.method == 'GET') {
        r.response.write('''<?xml version="1.0"?><root><device><friendlyName>Freebox Server</friendlyName>
<deviceList><device><serviceList><service><serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
<controlURL>/ctl/IPConn</controlURL></service></serviceList></device></deviceList></device></root>''');
      } else {
        final body = await utf8.decodeStream(r);
        final action = r.headers.value('SOAPAction')!;
        calls.add('$action $body');
        if (action.contains('GetExternalIPAddress')) {
          r.response.write('<s:Envelope><s:Body><u:R><NewExternalIPAddress>82.64.10.20</NewExternalIPAddress></u:R></s:Body></s:Envelope>');
        } else {
          r.response.write('<s:Envelope><s:Body/></s:Envelope>');
        }
      }
      await r.response.close();
    });
    final c = UpnpClient(location: Uri.parse('http://127.0.0.1:${srv.port}/desc.xml'));
    final res = await c.openPort(port: 53518, localIp: '192.168.1.20');
    expect(res.mapped, isTrue);
    expect(res.externalIp, '82.64.10.20');
    expect(res.gatewayName, 'Freebox Server');
    expect(isPublicIPv4(res.externalIp), isTrue);
    expect(isPublicIPv4('100.70.1.2'), isFalse); // IP partagée opérateur
    final add = calls.firstWhere((x) => x.contains('AddPortMapping'));
    expect(add, contains('<NewInternalClient>192.168.1.20</NewInternalClient>'));
    expect(add, contains('<NewExternalPort>53518</NewExternalPort>'));
    await srv.close(force: true);
  });

  group('accès à distance', () {
    late Node pc, phone;
    late Directory docs, depot;

    setUp(() async {
      pc = Node('PC Bureau', await Directory.systemTemp.createTemp('tr_pc'), DevicePlatform.linux);
      phone = Node('Tel Quentin', await Directory.systemTemp.createTemp('tr_tel'), DevicePlatform.android);
      await pc.boot();
      await phone.boot();
      // Le téléphone s'appaire avec le PC (sur le réseau local).
      final peer = await phone.engine.probe('127.0.0.1', pc.engine.port);
      await phone.engine.pair(peer, (n, e) async => pc.lastPrompt!.code);
      // Partages du PC
      docs = Directory(p.join(pc.root.path, 'Documents'))..createSync();
      depot = Directory(p.join(pc.root.path, 'Depot'))..createSync();
      await mk(p.join(docs.path, 'cours.pdf'), 300000, 1);
      await mk(p.join(docs.path, 'Photos', 'a.jpg'), 120000, 2);
      await mk(p.join(docs.path, 'Photos', 'Vacances', 'b.jpg'), 9 * 1024 * 1024, 3);
      pc.engine.settings.shares = [
        SharedFolder(path: docs.path, name: 'Documents'),
        SharedFolder(path: depot.path, name: 'Dépôt', writable: true),
      ];
    });

    tearDown(() async {
      await Future.delayed(const Duration(milliseconds: 600));
      await pc.engine.stop();
      await phone.engine.stop();
      for (final d in [pc.root, phone.root]) {
        try {
          await d.delete(recursive: true);
        } catch (_) {}
      }
    });

    test('le téléphone parcourt et télécharge les dossiers partagés du PC', () async {
      final e = phone.engine;
      final id = pc.engine.identity.id;
      final roots = await e.remoteRoots(id);
      expect(roots.map((r) => r.name), ['Documents', 'Dépôt']);
      final docsId = roots.first.id;
      final l = await e.remoteList(id, docsId, '');
      expect(l.first.name, 'Photos');
      expect(l.first.isDir, isTrue);
      expect(l.last.name, 'cours.pdf');
      // Sortir du partage est impossible.
      expect(() => e.remoteList(id, docsId, '../Depot'), throwsA(anything));
      await e.download(id, docsId, ['Photos', 'cours.pdf']);
      final j = await waitFor(e, (j) => j.direction == TransferDirection.receive);
      expect(j.status, TransferStatus.done, reason: j.error);
      expect(await sha(p.join(phone.recvDir, 'Photos', 'Vacances', 'b.jpg')), await sha(p.join(docs.path, 'Photos', 'Vacances', 'b.jpg')));
      expect(await sha(p.join(phone.recvDir, 'cours.pdf')), await sha(p.join(docs.path, 'cours.pdf')));
    });

    test('dépôt dans un dossier en écriture (sans confirmation) et refus en lecture seule', () async {
      final e = phone.engine;
      final id = pc.engine.identity.id;
      pc.accept = false; // la confirmation n'est pas demandée pour un dépôt
      final roots = await e.remoteRoots(id);
      final f = await mk(p.join(phone.root.path, 'scan.pdf'), 50000, 4);
      await e.upload(id, [LocalFileSource(f.path)], share: roots[1].id, path: '');
      final j = await waitFor(e, (j) => j.direction == TransferDirection.send);
      expect(j.status, TransferStatus.done, reason: j.error);
      expect(File(p.join(depot.path, 'scan.pdf')).existsSync(), isTrue);
      expect(pc.incoming, 0);
      await e.upload(id, [LocalFileSource(f.path)], share: roots[0].id, path: '');
      final j2 = await waitFor(e, (x) => x.direction == TransferDirection.send && x.id != j.id);
      expect(j2.status, TransferStatus.failed);
      expect(j2.error, contains('lecture seule'));
    });

    test('téléphone injoignable (4G) : le PC passe par le canal inverse', () async {
      final tel = phone.engine.identity.id;
      // Le PC ne peut pas joindre le téléphone (comme derrière l'opérateur 4G).
      pc.engine.trust.get(tel)!
        ..lastAddress = '127.0.0.9'
        ..lastPort = 9;
      // Partage côté téléphone
      final dcim = Directory(p.join(phone.root.path, 'DCIM'))..createSync();
      await mk(p.join(dcim.path, 'Camera', 'VID_001.mp4'), 12 * 1024 * 1024 + 5, 7);
      phone.engine.settings
        ..shares = [SharedFolder(path: dcim.path, name: 'Appareil photo', writable: true)]
        ..remoteAccess = true;
      await phone.engine.applyRemoteSettings();
      // Attente de l'ouverture du canal
      final end = DateTime.now().add(const Duration(seconds: 20));
      while (!pc.engine.tunnels.isActive(tel) && DateTime.now().isBefore(end)) {
        await Future.delayed(const Duration(milliseconds: 100));
      }
      expect(pc.engine.tunnels.isActive(tel), isTrue);
      expect(pc.engine.isReachable(tel), isTrue);

      // Parcourir le téléphone depuis le PC
      final roots = await pc.engine.remoteRoots(tel);
      expect(roots.single.name, 'Appareil photo');
      final l = await pc.engine.remoteList(tel, roots.single.id, 'Camera');
      expect(l.single.name, 'VID_001.mp4');

      // Récupérer une vidéo du téléphone : il l'envoie, réception sans confirmation.
      pc.accept = false;
      await pc.engine.download(tel, roots.single.id, ['Camera/VID_001.mp4']);
      final got = await waitFor(pc.engine, (j) => j.direction == TransferDirection.receive);
      expect(got.status, TransferStatus.done, reason: got.error);
      expect(await sha(p.join(pc.recvDir, 'VID_001.mp4')), await sha(p.join(dcim.path, 'Camera', 'VID_001.mp4')));

      // Envoyer du PC vers le téléphone : le téléphone vient télécharger.
      final doc = await mk(p.join(pc.root.path, 'facture.pdf'), 3 * 1024 * 1024, 9);
      await pc.engine.sendSmart(tel, [LocalFileSource(doc.path)]);
      final sent = await waitFor(pc.engine, (j) => j.direction == TransferDirection.send);
      expect(sent.status, TransferStatus.done, reason: sent.error);
      expect(await sha(p.join(phone.recvDir, 'facture.pdf')), await sha(doc.path));
      expect(phone.incoming, 1); // le téléphone a confirmé la réception

      // Dépôt direct dans un dossier du téléphone ouvert en écriture.
      await pc.engine.upload(tel, [LocalFileSource(doc.path)], share: roots.single.id, path: 'Camera');
      final end2 = DateTime.now().add(const Duration(seconds: 30));
      while (!File(p.join(dcim.path, 'Camera', 'facture.pdf')).existsSync() && DateTime.now().isBefore(end2)) {
        await Future.delayed(const Duration(milliseconds: 100));
      }
      expect(await sha(p.join(dcim.path, 'Camera', 'facture.pdf')), await sha(doc.path));
    }, timeout: const Timeout(Duration(minutes: 2)));

    test('appairage refusé depuis Internet', () async {
      expect(isLocalAddress('82.64.10.20'), isFalse);
      expect(isLocalAddress('2a01:e0a::1'), isFalse);
      expect(isLocalAddress('192.168.1.5'), isTrue);
      expect(isLocalAddress('fe80::1'), isTrue);
    });
  });
}
