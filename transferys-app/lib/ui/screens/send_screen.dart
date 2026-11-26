// Écran « Envoyer » : orbite des appareils proches + choix des fichiers.
//
// Cet appareil est au centre ; les appareils de confiance sont sur l'anneau
// intérieur, les nouveaux sur l'anneau extérieur. Toucher une bulle envoie
// la sélection (ou lance l'appairage).
import 'dart:math' as math;

import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/format.dart';
import '../app_state.dart';
import '../brand.dart';
import '../widgets.dart';
import 'add_device_screen.dart';
import 'help_screen.dart';

class SendScreen extends StatefulWidget {
  const SendScreen({super.key});
  @override
  State<SendScreen> createState() => _SendScreenState();
}

class _SendScreenState extends State<SendScreen> {
  bool _dragging = false;

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final wide = MediaQuery.sizeOf(context).width >= 980;

    final orbitPart = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const _Header(),
      if (app.networkError != null) _Banner(text: app.networkError!, icon: Icons.warning_amber_rounded),
      if (app.localAddresses.isEmpty)
        const _Banner(
          icon: Icons.wifi_off_rounded,
          text: 'Aucun Wi-Fi détecté. Connectez cet appareil au même réseau que l\'autre, ou au point d\'accès du téléphone.',
        ),
      const _OrbitZone(),
    ]);
    const selectionPart = _SelectionZone();

    final content = wide
        ? SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(28, 12, 28, 32),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(flex: 6, child: orbitPart),
              const SizedBox(width: 24),
              const Expanded(flex: 5, child: Padding(padding: EdgeInsets.only(top: 92), child: selectionPart)),
            ]),
          )
        : ListView(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
            children: [orbitPart, selectionPart],
          );

    if (!app.isDesktop) return content;
    final cs = Theme.of(context).colorScheme;
    return DropTarget(
      onDragDone: (d) {
        setState(() => _dragging = false);
        app.addPaths(d.files.map((f) => f.path).toList());
      },
      onDragEntered: (_) => setState(() => _dragging = true),
      onDragExited: (_) => setState(() => _dragging = false),
      child: Stack(children: [
        content,
        if (_dragging)
          Positioned.fill(
            child: IgnorePointer(
              child: Container(
                margin: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: cs.primary.withValues(alpha: 0.10),
                  border: Border.all(color: cs.primary, width: 3),
                  borderRadius: BorderRadius.circular(Radii.zone),
                ),
                child: Center(
                  child: Column(mainAxisSize: MainAxisSize.min, children: [
                    Icon(Icons.file_download_rounded, size: 64, color: cs.primary),
                    const SizedBox(height: 10),
                    Text('Déposez pour ajouter à l\'envoi', style: Theme.of(context).textTheme.headlineSmall),
                  ]),
                ),
              ),
            ),
          ),
      ]),
    );
  }
}

// ------------------------------------------------------------------ en-tête
class _Header extends StatelessWidget {
  const _Header();
  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final t = Theme.of(context);
    final cs = t.colorScheme;
    final online = app.localAddresses.isNotEmpty;
    final ip = online ? app.localAddresses.first.address.address : null;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 8, 4, 18),
      child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(app.settings.deviceName, style: t.textTheme.headlineMedium, maxLines: 1, overflow: TextOverflow.ellipsis),
            const SizedBox(height: 4),
            Row(children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(color: online ? okGreen : cs.outline, shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  online ? 'Prêt à recevoir, adresse $ip' : 'Hors réseau',
                  style: t.textTheme.bodyMedium?.copyWith(color: cs.onSurfaceVariant),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ]),
          ]),
        ),
        IconButton.filledTonal(
          tooltip: 'Actualiser',
          onPressed: app.scanning ? null : app.refreshDevices,
          icon: app.scanning
              ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh_rounded),
        ),
        const SizedBox(width: 6),
        IconButton.filledTonal(
          tooltip: 'Ajouter un appareil (QR code, adresse IP)',
          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const AddDeviceScreen())),
          icon: const Icon(Icons.qr_code_2_rounded),
        ),
      ]),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.text, required this.icon});
  final String text;
  final IconData icon;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.fromLTRB(14, 10, 6, 10),
      decoration: BoxDecoration(color: cs.errorContainer, borderRadius: BorderRadius.circular(Radii.item)),
      child: Row(children: [
        Icon(icon, color: cs.onErrorContainer),
        const SizedBox(width: 12),
        Expanded(child: Text(text, style: TextStyle(color: cs.onErrorContainer))),
        TextButton(
          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const HelpScreen())),
          child: const Text('Aide'),
        ),
      ]),
    );
  }
}

// ------------------------------------------------------------------ orbite
class _OrbitZone extends StatelessWidget {
  const _OrbitZone();

  static const _maxOnOrbit = 8;

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final t = Theme.of(context);
    final devices = app.devices;
    final onOrbit = devices.take(_maxOnOrbit).toList();
    final extra = devices.skip(_maxOnOrbit).toList();
    final n = app.selection.length;
    final hint = devices.isEmpty
        ? 'Recherche des appareils sur le Wi-Fi… Ouvrez Transferys sur l\'autre appareil.'
        : (n == 0
            ? 'Choisissez des fichiers, puis touchez un appareil.'
            : 'Touchez un appareil pour envoyer $n fichier${n > 1 ? 's' : ''}.');
    return Zone(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 16),
      child: Column(children: [
        LayoutBuilder(builder: (c, box) {
          final size = math.min(box.maxWidth, 460.0);
          return SizedBox(width: size, height: size < 420 ? size * 1.05 : size * 0.94, child: _Orbit(devices: onOrbit));
        }),
        const SizedBox(height: 4),
        Text(hint, textAlign: TextAlign.center, style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant)),
        if (devices.isEmpty) ...[
          const SizedBox(height: 8),
          TextButton.icon(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const HelpScreen())),
            icon: const Icon(Icons.help_outline_rounded),
            label: const Text('Il n\'apparaît pas ?'),
          ),
        ],
        for (final d in extra) _DeviceRow(d),
      ]),
    );
  }
}

class _Orbit extends StatefulWidget {
  const _Orbit({required this.devices});
  final List<DeviceEntry> devices;
  @override
  State<_Orbit> createState() => _OrbitState();
}

class _OrbitState extends State<_Orbit> with SingleTickerProviderStateMixin {
  // Une seule animation (l'onde). Pour ménager la batterie, elle ne joue que
  // quelques cycles : à l'ouverture et quand la liste des appareils change.
  late final AnimationController _wave = AnimationController(vsync: this, duration: const Duration(milliseconds: 3200))
    ..addStatusListener((s) {
      if (s == AnimationStatus.completed) {
        _cycles--;
        if (_cycles > 0) {
          _wave.forward(from: 0);
        } else {
          _wave.reset();
          if (mounted) setState(() {});
        }
      }
    });
  int _cycles = 0;
  late final AppLifecycleListener _life = AppLifecycleListener(onResume: _pulse);

  void _pulse() {
    if (!mounted || MediaQuery.disableAnimationsOf(context)) return;
    _cycles = 6; // environ 20 secondes
    if (!_wave.isAnimating) _wave.forward(from: 0);
  }

  @override
  void initState() {
    super.initState();
    _life; // écoute du retour au premier plan
    WidgetsBinding.instance.addPostFrameCallback((_) => _pulse());
  }

  @override
  void didUpdateWidget(_Orbit old) {
    super.didUpdateWidget(old);
    final before = old.devices.map((d) => '${d.id}${d.online}').join();
    final now = widget.devices.map((d) => '${d.id}${d.online}').join();
    if (before != now) _pulse();
  }

  @override
  void dispose() {
    _life.dispose();
    _wave.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final cs = Theme.of(context).colorScheme;
    return LayoutBuilder(builder: (c, box) {
      final w = box.maxWidth, h = box.maxHeight;
      final center = Offset(w / 2, h / 2);
      // Petit écran (téléphone) : bulles plus compactes, nom seul sous la bulle.
      final compact = w < 420;
      final bubble = compact ? 52.0 : 60.0;
      final labelW = compact ? 96.0 : 112.0;
      final labelH = compact ? 26.0 : 48.0;
      final core = compact ? 28.0 : 34.0; // rayon du disque central
      // L'anneau extérieur laisse la place des étiquettes en bas et sur les côtés.
      final rMax = math.min(w / 2 - labelW / 2 + 4, h / 2 - bubble / 2 - labelH);
      // Anneau intérieur assez loin du centre pour que les noms ne le touchent pas.
      final inner = math.max(rMax * 0.6, core + bubble / 2 + labelH + 6);
      final outer = rMax;

      // Confiance sur l'anneau intérieur, nouveaux sur l'extérieur.
      final trusted = widget.devices.where((d) => d.isTrusted).toList();
      final fresh = widget.devices.where((d) => !d.isTrusted).toList();
      final placed = <(DeviceEntry, Offset)>[];
      void place(List<DeviceEntry> list, double r, double start) {
        for (var i = 0; i < list.length; i++) {
          final a = start + 2 * math.pi * i / list.length;
          placed.add((list[i], center + Offset(math.cos(a) * r, math.sin(a) * r)));
        }
      }

      // Départs décalés pour que les bulles des deux anneaux ne s'alignent pas.
      place(trusted, inner, -math.pi / 2 - 0.5);
      place(fresh, outer, math.pi * 0.22);

      return Stack(clipBehavior: Clip.none, children: [
        Positioned.fill(
          child: AnimatedBuilder(
            animation: _wave,
            builder: (_, __) => CustomPaint(
              painter: _RingsPainter(
                center: center,
                radii: [inner, outer],
                core: core,
                wave: _wave.isAnimating ? _wave.value : null,
                ring: cs.outlineVariant,
                waveColor: cs.primary,
              ),
            ),
          ),
        ),
        // Cet appareil, au centre
        Positioned(
          left: center.dx - core,
          top: center.dy - core,
          child: Container(
            width: core * 2,
            height: core * 2,
            decoration: const BoxDecoration(
              shape: BoxShape.circle,
              gradient: LinearGradient(colors: [brandBlue, brandCyan], begin: Alignment.topLeft, end: Alignment.bottomRight),
            ),
            child: Icon(app.isAndroid ? Icons.smartphone_rounded : Icons.computer_rounded, color: Colors.white, size: core * 0.95),
          ),
        ),
        for (final (d, pos) in placed)
          Positioned(
            left: pos.dx - labelW / 2,
            top: pos.dy - bubble / 2,
            width: labelW,
            child: _Bubble(d: d, size: bubble, showStatus: !compact),
          ),
      ]);
    });
  }
}

class _RingsPainter extends CustomPainter {
  _RingsPainter({required this.center, required this.radii, required this.wave, required this.ring, required this.waveColor, required this.core});
  final Offset center;
  final double core;
  final List<double> radii;
  final double? wave;
  final Color ring;
  final Color waveColor;

  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5
      ..color = ring;
    for (final r in radii) {
      canvas.drawCircle(center, r, p);
    }
    final v = wave;
    if (v != null) {
      final r = core + (radii.last - core) * Curves.easeOut.transform(v);
      final wp = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..color = waveColor.withValues(alpha: 0.40 * (1 - v));
      canvas.drawCircle(center, r, wp);
    }
  }

  @override
  bool shouldRepaint(_RingsPainter o) => o.wave != wave || o.ring != ring || o.center != center || o.radii.last != radii.last;
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.d, required this.size, this.showStatus = true});
  final DeviceEntry d;
  final double size;
  final bool showStatus;

  @override
  Widget build(BuildContext context) {
    final app = context.read<AppState>();
    final t = Theme.of(context);
    final cs = t.colorScheme;
    final Color fill;
    final Color fg;
    if (!d.online) {
      fill = cs.surfaceContainerHigh;
      fg = cs.outline;
    } else if (d.isTrusted) {
      fill = cs.primary;
      fg = cs.onPrimary;
    } else {
      fill = Theme.of(context).brightness == Brightness.dark ? nightSurface : Colors.white;
      fg = cs.primary;
    }
    final status = !d.online
        ? 'Hors ligne'
        : d.remote
            ? 'À distance'
            : (d.isTrusted ? (d.trusted!.autoAccept ? 'Accepte tout' : 'De confiance') : 'Nouveau');
    return Tooltip(
      message: d.isTrusted ? 'Envoyer à ${d.name}' : 'Appairer ${d.name}',
      child: InkWell(
        borderRadius: BorderRadius.circular(Radii.item),
        onTap: (d.online || d.isTrusted) ? () => app.sendTo(d) : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Stack(clipBehavior: Clip.none, children: [
              Container(
                width: size,
                height: size,
                decoration: BoxDecoration(
                  color: fill,
                  shape: BoxShape.circle,
                  border: d.isTrusted ? null : Border.all(color: cs.primary, width: 2),
                ),
                child: Icon(platformIcon(d.platform), color: fg, size: size * 0.46),
              ),
              if (d.remote)
                Positioned(
                  right: -2,
                  bottom: -2,
                  child: Container(
                    padding: const EdgeInsets.all(3),
                    decoration: BoxDecoration(
                      color: brandCyan,
                      shape: BoxShape.circle,
                      border: Border.all(color: Theme.of(context).brightness == Brightness.dark ? nightSurface : Colors.white, width: 2),
                    ),
                    child: const Icon(Icons.public_rounded, size: 14, color: Colors.white),
                  ),
                ),
            ]),
            const SizedBox(height: 6),
            Text(d.name, maxLines: 1, overflow: TextOverflow.ellipsis, textAlign: TextAlign.center, style: t.textTheme.labelLarge),
            if (showStatus)
              Text(status,
                maxLines: 1,
                textAlign: TextAlign.center,
                style: t.textTheme.labelSmall?.copyWith(color: d.remote ? brandCyan : cs.onSurfaceVariant)),
          ]),
        ),
      ),
    );
  }
}

/// Appareils au-delà de ce que l'orbite peut afficher.
class _DeviceRow extends StatelessWidget {
  const _DeviceRow(this.d);
  final DeviceEntry d;
  @override
  Widget build(BuildContext context) {
    final app = context.read<AppState>();
    return ListTile(
      leading: PlatformAvatar(platform: d.platform, online: d.online),
      title: Text(d.name),
      subtitle: Text(d.isTrusted ? 'De confiance' : 'Nouvel appareil'),
      trailing: const Icon(Icons.send_rounded),
      onTap: () => app.sendTo(d),
    );
  }
}

// ------------------------------------------------------------- sélection
class _SelectionZone extends StatelessWidget {
  const _SelectionZone();

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final t = Theme.of(context);
    final cs = t.colorScheme;
    final sel = app.selection;
    final actions = [
      _PickTile(icon: Icons.upload_file_rounded, label: 'Fichiers', onTap: app.pickFiles, primary: true),
      if (app.isAndroid) _PickTile(icon: Icons.photo_library_rounded, label: 'Photos et vidéos', onTap: app.pickMedia),
      _PickTile(icon: Icons.folder_rounded, label: 'Dossier', onTap: app.pickFolder),
    ];
    return Zone(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Expanded(
            child: Text(
              sel.isEmpty ? 'À envoyer' : '${sel.length} fichier${sel.length > 1 ? 's' : ''}, ${formatSize(app.selectionSize)}',
              style: t.textTheme.titleLarge,
            ),
          ),
          if (sel.isNotEmpty) TextButton(onPressed: app.clearSelection, child: const Text('Tout retirer')),
        ]),
        const SizedBox(height: 12),
        if (sel.isEmpty)
          Container(
            padding: const EdgeInsets.symmetric(vertical: 22, horizontal: 12),
            margin: const EdgeInsets.only(bottom: 14),
            decoration: BoxDecoration(
              color: cs.surfaceContainerLow,
              borderRadius: BorderRadius.circular(Radii.item),
              border: Border.all(color: cs.outlineVariant, width: 1.5),
            ),
            child: Column(children: [
              Icon(app.isDesktop ? Icons.file_download_outlined : Icons.touch_app_outlined, size: 36, color: cs.primary),
              const SizedBox(height: 8),
              Text(
                app.isDesktop ? 'Glissez vos fichiers ou dossiers ici' : 'Ajoutez des fichiers avec les boutons ci-dessous',
                textAlign: TextAlign.center,
                style: t.textTheme.titleMedium,
              ),
              const SizedBox(height: 2),
              Text('Tous types, sans limite de taille.', style: t.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
            ]),
          )
        else
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 260),
            child: ListView.separated(
              shrinkWrap: true,
              padding: const EdgeInsets.only(bottom: 14),
              itemCount: sel.length,
              separatorBuilder: (_, __) => const SizedBox(height: 6),
              itemBuilder: (c, i) => Container(
                decoration: BoxDecoration(color: cs.surfaceContainerLow, borderRadius: BorderRadius.circular(Radii.chip + 2)),
                padding: const EdgeInsets.fromLTRB(10, 8, 4, 8),
                child: Row(children: [
                  FileBadge(name: sel[i].relPath),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(sel[i].relPath, maxLines: 1, overflow: TextOverflow.ellipsis, style: t.textTheme.titleSmall),
                      Text(formatSize(sel[i].size), style: t.textTheme.bodySmall?.copyWith(color: cs.onSurfaceVariant)),
                    ]),
                  ),
                  IconButton(
                    tooltip: 'Retirer',
                    icon: const Icon(Icons.close_rounded, size: 20),
                    onPressed: () => app.removeSourceAt(i),
                  ),
                ]),
              ),
            ),
          ),
        Row(children: [
          for (var i = 0; i < actions.length; i++) ...[
            if (i > 0) const SizedBox(width: 8),
            Expanded(child: actions[i]),
          ],
        ]),
        const SizedBox(height: 10),
        Material(
          color: Colors.transparent,
          child: SwitchListTile(
            contentPadding: const EdgeInsets.only(left: 4),
            secondary: Icon(Icons.drive_file_move_rounded, color: cs.primary),
            title: const Text('Choisir le dossier d\'arrivée'),
            subtitle: Text(app.chooseDestination
                ? 'Vous choisirez le dossier sur l\'autre appareil au moment d\'envoyer.'
                : 'Sinon : son dossier de réception habituel.'),
            value: app.chooseDestination,
            onChanged: app.setChooseDestination,
          ),
        ),
      ]),
    );
  }
}

class _PickTile extends StatelessWidget {
  const _PickTile({required this.icon, required this.label, required this.onTap, this.primary = false});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool primary;
  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final bg = primary ? cs.primary : cs.primary.withValues(alpha: 0.10);
    final fg = primary ? cs.onPrimary : cs.primary;
    return Material(
      color: bg,
      borderRadius: BorderRadius.circular(Radii.item),
      child: InkWell(
        borderRadius: BorderRadius.circular(Radii.item),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 6),
          child: Column(children: [
            Icon(icon, color: fg),
            const SizedBox(height: 6),
            Text(label, textAlign: TextAlign.center, maxLines: 2, style: Theme.of(context).textTheme.labelMedium?.copyWith(color: fg)),
          ]),
        ),
      ),
    );
  }
}
