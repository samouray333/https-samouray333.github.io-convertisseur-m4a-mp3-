// Ajouter un appareil : scanner un QR code (téléphone), afficher son QR
// code (PC et téléphone), ou saisir une adresse IP.
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';
import 'package:provider/provider.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../network/net_utils.dart';
import '../../network/qr_payload.dart';
import '../app_state.dart';

class AddDeviceScreen extends StatelessWidget {
  const AddDeviceScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final tabs = <Tab>[
      if (app.isAndroid) const Tab(icon: Icon(Icons.qr_code_scanner_rounded), text: 'Scanner'),
      const Tab(icon: Icon(Icons.qr_code_2_rounded), text: 'Mon QR code'),
      const Tab(icon: Icon(Icons.edit_note_rounded), text: 'Adresse IP'),
    ];
    return DefaultTabController(
      length: tabs.length,
      child: Scaffold(
        appBar: AppBar(title: const Text('Ajouter un appareil'), bottom: TabBar(tabs: tabs)),
        body: TabBarView(children: [
          if (app.isAndroid) const _ScanTab(),
          const _MyQrTab(),
          const _ManualTab(),
        ]),
      ),
    );
  }
}

Future<void> _afterFound(BuildContext context, AppState app, String id) async {
  final dev = app.devices.where((d) => d.id == id).firstOrNull;
  if (dev == null) return;
  if (!dev.isTrusted && dev.peer != null) {
    final t = await app.pairWith(dev.peer!);
    if (t == null) return;
  } else {
    app.toast('${dev.name} est prêt.');
  }
  if (context.mounted) Navigator.of(context).pop();
}

class _ScanTab extends StatefulWidget {
  const _ScanTab();
  @override
  State<_ScanTab> createState() => _ScanTabState();
}

class _ScanTabState extends State<_ScanTab> {
  final _ctrl = MobileScannerController(formats: const [BarcodeFormat.qrCode]);
  bool _busy = false;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _onDetect(BarcodeCapture cap) async {
    if (_busy) return;
    final raw = cap.barcodes.map((b) => b.rawValue).whereType<String>().firstOrNull;
    if (raw == null) return;
    final payload = QrPayload.tryParse(raw);
    if (payload == null) return;
    setState(() => _busy = true);
    await _ctrl.stop();
    final app = context.read<AppState>();
    // Essaie chaque adresse du PC (Wi-Fi, Ethernet, point d'accès).
    for (final ip in payload.addresses) {
      try {
        final peer = await app.engine.probe(ip, payload.port, expectedFingerprint: payload.fingerprint);
        if (!mounted) return;
        await _afterFound(context, app, peer.id);
        return;
      } catch (_) {}
    }
    if (!mounted) return;
    app.showErrorDialog('Connexion impossible',
        '${payload.name} ne répond sur aucune de ses adresses (${payload.addresses.join(', ')}). Vérifiez que les deux appareils sont sur le même Wi-Fi. Sur PC, le pare-feu Windows bloque peut-être Transferys.');
    setState(() => _busy = false);
    await _ctrl.start();
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Expanded(
        child: Stack(alignment: Alignment.center, children: [
          MobileScanner(
            controller: _ctrl,
            onDetect: _onDetect,
            errorBuilder: (c, e) => Padding(
              padding: const EdgeInsets.all(24),
              child: Text(
                e.errorCode == MobileScannerErrorCode.permissionDenied
                    ? 'Transferys a besoin de l\'appareil photo pour lire le QR code affiché sur le PC. Autorisez-le dans les réglages Android (Applis > Transferys > Autorisations).'
                    : 'Appareil photo indisponible : ${e.errorDetails?.message ?? e.errorCode.name}',
                textAlign: TextAlign.center,
              ),
            ),
          ),
          IgnorePointer(
            child: Container(
              width: 240,
              height: 240,
              decoration: BoxDecoration(border: Border.all(color: Colors.white, width: 3), borderRadius: BorderRadius.circular(20)),
            ),
          ),
          if (_busy) const CircularProgressIndicator(),
        ]),
      ),
      const Padding(
        padding: EdgeInsets.all(16),
        child: Text('Sur le PC : Transferys > Envoyer > Ajouter > « Mon QR code ». Visez le QR code avec le téléphone.',
            textAlign: TextAlign.center),
      ),
    ]);
  }
}

class _MyQrTab extends StatelessWidget {
  const _MyQrTab();
  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final t = Theme.of(context);
    final ips = app.localAddresses.map((a) => a.address.address).toList();
    if (ips.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Aucun réseau Wi-Fi : connectez cet appareil à un réseau pour afficher son QR code.', textAlign: TextAlign.center),
        ),
      );
    }
    final payload = QrPayload(
      id: app.engine.identity.id,
      name: app.settings.deviceName,
      platform: app.engine.platform,
      addresses: ips,
      port: app.engine.port,
      fingerprint: app.engine.identity.fingerprint,
    );
    return ListView(padding: const EdgeInsets.all(24), children: [
      Center(
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(20)),
          child: QrImageView(data: payload.encode(), size: 260, backgroundColor: Colors.white),
        ),
      ),
      const SizedBox(height: 20),
      Text('Scannez ce code avec Transferys sur le téléphone', style: t.textTheme.titleMedium, textAlign: TextAlign.center),
      const SizedBox(height: 8),
      Text('Téléphone : Envoyer > Ajouter > Scanner', textAlign: TextAlign.center, style: t.textTheme.bodyMedium),
      const SizedBox(height: 18),
      Card(
        child: ListTile(
          leading: const Icon(Icons.lan_outlined),
          title: Text(ips.join('  •  ')),
          subtitle: Text('Port ${app.engine.port} • à saisir dans « Adresse IP » si besoin'),
        ),
      ),
    ]);
  }
}

class _ManualTab extends StatefulWidget {
  const _ManualTab();
  @override
  State<_ManualTab> createState() => _ManualTabState();
}

class _ManualTabState extends State<_ManualTab> {
  final _ip = TextEditingController();
  final _port = TextEditingController(text: '53518');
  bool _busy = false;
  String? _err;

  @override
  void dispose() {
    _ip.dispose();
    _port.dispose();
    super.dispose();
  }

  Future<void> _go() async {
    final ip = _ip.text.trim();
    if (!isValidIPv4(ip)) {
      setState(() => _err = 'Adresse invalide. Exemple : 192.168.1.25');
      return;
    }
    setState(() {
      _busy = true;
      _err = null;
    });
    final app = context.read<AppState>();
    final peer = await app.connectManual(ip, int.tryParse(_port.text) ?? 53518);
    if (!mounted) return;
    setState(() => _busy = false);
    if (peer != null) await _afterFound(context, app, peer.id);
  }

  @override
  Widget build(BuildContext context) {
    return ListView(padding: const EdgeInsets.all(24), children: [
      const Text('L\'adresse IP de l\'autre appareil s\'affiche en haut de son écran « Envoyer » (ex. 192.168.1.25).'),
      const SizedBox(height: 18),
      TextField(
        controller: _ip,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(labelText: 'Adresse IP', hintText: '192.168.1.25', errorText: _err, border: const OutlineInputBorder()),
        onSubmitted: (_) => _go(),
      ),
      const SizedBox(height: 12),
      TextField(
        controller: _port,
        keyboardType: TextInputType.number,
        decoration: const InputDecoration(labelText: 'Port', border: OutlineInputBorder()),
      ),
      const SizedBox(height: 18),
      FilledButton.icon(
        onPressed: _busy ? null : _go,
        icon: _busy ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.link_rounded),
        label: const Text('Se connecter'),
      ),
    ]);
  }
}
