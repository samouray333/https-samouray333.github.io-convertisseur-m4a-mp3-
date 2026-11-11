// Guide au premier lancement (3 écrans).
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../platform/android_bridge.dart';
import '../app_state.dart';
import '../brand.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key, this.replay = false});
  final bool replay;
  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _page = PageController();
  int _index = 0;
  late final TextEditingController _name;

  @override
  void initState() {
    super.initState();
    _name = TextEditingController(text: context.read<AppState>().settings.deviceName);
  }

  @override
  void dispose() {
    _page.dispose();
    _name.dispose();
    super.dispose();
  }

  Future<void> _finish() async {
    final app = context.read<AppState>();
    final n = _name.text.trim();
    await app.updateSettings((s) {
      if (n.isNotEmpty) s.deviceName = n;
      s.onboardingDone = true;
    });
    if (Platform.isAndroid && !widget.replay) {
      await AndroidBridge.requestNotificationPermission();
      await AndroidBridge.requestLegacyStorage();
    }
    if (widget.replay && mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final pages = [
      _Page(
        visual: const BrandLogo(size: 120),
        title: 'Bienvenue dans Transferys',
        text: 'Envoyez photos, vidéos, documents et dossiers entiers entre votre PC Windows et votre téléphone Android. Sans câble, sans limite de taille, sans Internet.',
      ),
      _Page(
        visual: Icon(Icons.wifi_rounded, size: 110, color: t.colorScheme.primary),
        title: 'Un seul Wi-Fi pour les deux',
        text: 'Ouvrez Transferys sur le PC et sur le téléphone, connectés au même Wi-Fi (ou le PC branché sur le point d\'accès du téléphone). Ils se trouvent tout seuls. Sinon : QR code ou adresse IP, via le bouton « Ajouter ».',
      ),
      _Page(
        visual: Icon(Icons.verified_user_rounded, size: 110, color: t.colorScheme.primary),
        title: 'Un code, une seule fois',
        text: 'Au premier envoi, un code à 6 chiffres s\'affiche sur l\'appareil qui reçoit : saisissez-le sur l\'autre. Ensuite, tout est chiffré et les deux appareils se reconnaissent.',
        extra: Padding(
          padding: const EdgeInsets.only(top: 22),
          child: SizedBox(
            width: 340,
            child: TextField(
              controller: _name,
              maxLength: 40,
              decoration: const InputDecoration(
                labelText: 'Nom de cet appareil',
                hintText: 'ex. PC Bureau, Tel Quentin',
                border: OutlineInputBorder(),
              ),
            ),
          ),
        ),
      ),
    ];
    final last = _index == pages.length - 1;
    return Scaffold(
      body: SafeArea(
        child: Column(children: [
          Align(
            alignment: Alignment.topRight,
            child: TextButton(onPressed: _finish, child: Text(widget.replay ? 'Fermer' : 'Passer')),
          ),
          Expanded(
            child: PageView(
              controller: _page,
              onPageChanged: (i) => setState(() => _index = i),
              children: pages,
            ),
          ),
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            for (var i = 0; i < pages.length; i++)
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.all(4),
                width: i == _index ? 22 : 8,
                height: 8,
                decoration: BoxDecoration(
                  color: i == _index ? t.colorScheme.primary : t.colorScheme.outlineVariant,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
          ]),
          Padding(
            padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
            child: SizedBox(
              width: 420,
              child: FilledButton(
                style: FilledButton.styleFrom(padding: const EdgeInsets.symmetric(vertical: 16)),
                onPressed: last
                    ? _finish
                    : () => _page.nextPage(duration: const Duration(milliseconds: 300), curve: Curves.easeOut),
                child: Text(last ? 'Commencer' : 'Suivant'),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

class _Page extends StatelessWidget {
  const _Page({required this.visual, required this.title, required this.text, this.extra});
  final Widget visual;
  final String title;
  final String text;
  final Widget? extra;
  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            visual,
            const SizedBox(height: 28),
            Text(title, style: t.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700), textAlign: TextAlign.center),
            const SizedBox(height: 14),
            Text(text, style: t.textTheme.bodyLarge, textAlign: TextAlign.center),
            if (extra != null) extra!,
          ]),
        ),
      ),
    );
  }
}
