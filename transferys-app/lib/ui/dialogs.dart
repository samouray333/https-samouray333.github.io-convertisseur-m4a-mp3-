// Dialogues : demande de réception, code d'appairage (affichage / saisie).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/format.dart';
import '../transfer/receiver.dart';
import '../transfer/server.dart';
import 'widgets.dart';

// ------------------------------------------------------ demande de réception
Future<bool> showIncomingDialog(BuildContext context, IncomingRequest r) async {
  final res = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (c) {
      final files = r.files;
      final shown = files.take(6).toList();
      return AlertDialog(
        icon: Align(widthFactor: 1, child: PlatformAvatar(platform: r.from.platform, size: 48)),
        title: Text('${r.from.name} veut vous envoyer'),
        content: SizedBox(
          width: 420,
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('${files.length} fichier(s) • ${formatSize(r.totalSize)}', style: Theme.of(c).textTheme.titleMedium),
            const SizedBox(height: 12),
            for (final f in shown)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(children: [
                  Icon(iconForFile(f.relPath), size: 20),
                  const SizedBox(width: 8),
                  Expanded(child: Text(f.relPath, overflow: TextOverflow.ellipsis)),
                  Text(formatSize(f.size), style: Theme.of(c).textTheme.bodySmall),
                ]),
              ),
            if (files.length > shown.length)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('… et ${files.length - shown.length} autre(s)', style: Theme.of(c).textTheme.bodySmall),
              ),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Refuser')),
          FilledButton.icon(
            onPressed: () => Navigator.pop(c, true),
            icon: const Icon(Icons.download_rounded),
            label: const Text('Accepter'),
          ),
        ],
      );
    },
  );
  return res ?? false;
}

// --------------------------------------------- affichage du code (récepteur)
class PairingCodeController {
  final _close = Completer<void>();
  void close() {
    if (!_close.isCompleted) _close.complete();
  }

  Future<void> get closed => _close.future;
}

/// Renvoie true si l'utilisateur a refusé.
Future<bool?> showPairingCodeDialog(BuildContext context, PairingPrompt p, PairingCodeController c, VoidCallback onApprove) {
  return showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => _AutoClose(signal: c.closed, child: _PairingCodeDialog(prompt: p, onApprove: onApprove)),
  );
}

class _PairingCodeDialog extends StatefulWidget {
  const _PairingCodeDialog({required this.prompt, required this.onApprove});
  final PairingPrompt prompt;
  final VoidCallback onApprove;
  @override
  State<_PairingCodeDialog> createState() => _PairingCodeDialogState();
}

class _PairingCodeDialogState extends State<_PairingCodeDialog> {
  bool _approved = false;

  @override
  Widget build(BuildContext context) {
    final p = widget.prompt;
    final t = Theme.of(context);
    final code = '${p.code.substring(0, 3)} ${p.code.substring(3)}';
    return AlertDialog(
      icon: const Icon(Icons.verified_user_outlined, size: 40),
      title: Text('« ${p.peerName} » veut s\'appairer'),
      content: SizedBox(
        width: 400,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(
            _approved
                ? 'Autorisé. Saisissez maintenant ce code sur « ${p.peerName} » :'
                : 'Si c\'est bien vous qui lancez cet appairage, cliquez sur Autoriser, puis saisissez ce code sur « ${p.peerName} ».',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 18),
          SelectableText(code,
              style: t.textTheme.displayMedium?.copyWith(fontWeight: FontWeight.w700, letterSpacing: 6, color: t.colorScheme.primary)),
          const SizedBox(height: 14),
          Text(
            'Un appareil de confiance peut vous envoyer des fichiers et parcourir vos dossiers partagés. Refusez si vous ne reconnaissez pas cet appareil.',
            textAlign: TextAlign.center,
            style: t.textTheme.bodySmall,
          ),
        ]),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context, true), child: Text(_approved ? 'Annuler' : 'Refuser')),
        if (!_approved)
          FilledButton.icon(
            onPressed: () {
              widget.onApprove();
              setState(() => _approved = true);
            },
            icon: const Icon(Icons.check_rounded),
            label: const Text('Autoriser'),
          ),
      ],
    );
  }
}

/// Ferme la route du dialogue quand [signal] se termine (une seule fois, et
/// uniquement cette route).
class _AutoClose extends StatefulWidget {
  const _AutoClose({required this.signal, required this.child});
  final Future<void> signal;
  final Widget child;
  @override
  State<_AutoClose> createState() => _AutoCloseState();
}

class _AutoCloseState extends State<_AutoClose> {
  @override
  void initState() {
    super.initState();
    widget.signal.then((_) {
      if (!mounted) return;
      final route = ModalRoute.of(context);
      if (route != null && route.isActive) Navigator.of(context).removeRoute(route);
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

// ------------------------------------------------- saisie du code (émetteur)
class CodeEntryController extends ChangeNotifier {
  String? peerName;
  String? error;
  bool waiting = true; // en attente de l'autre appareil
  Completer<String?>? _answer;
  bool _closed = false;
  final _closedSignal = Completer<void>();

  Future<String?> ask(String name, String? err) {
    peerName = name;
    error = err;
    waiting = false;
    _answer = Completer<String?>();
    notifyListeners();
    return _answer!.future;
  }

  void submit(String? code) {
    if (_answer != null && !_answer!.isCompleted) _answer!.complete(code);
    waiting = true;
    notifyListeners();
  }

  void close() {
    if (_closed) return;
    _closed = true;
    if (_answer != null && !_answer!.isCompleted) _answer!.complete(null);
    if (!_closedSignal.isCompleted) _closedSignal.complete();
  }
}

void showCodeEntryDialog(BuildContext context, String peerName, CodeEntryController c) {
  showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => _AutoClose(signal: c._closedSignal.future, child: _CodeEntryDialog(controller: c, initialName: peerName)),
  ).then((_) => c.close());
}

class _CodeEntryDialog extends StatefulWidget {
  const _CodeEntryDialog({required this.controller, required this.initialName});
  final CodeEntryController controller;
  final String initialName;
  @override
  State<_CodeEntryDialog> createState() => _CodeEntryDialogState();
}

class _CodeEntryDialogState extends State<_CodeEntryDialog> {
  final _text = TextEditingController();

  @override
  void initState() {
    super.initState();
    widget.controller.addListener(_changed);
  }

  void _changed() {
    if (!mounted) return;
    if (!widget.controller.waiting) _text.clear();
    setState(() {});
  }

  @override
  void dispose() {
    widget.controller.removeListener(_changed);
    _text.dispose();
    super.dispose();
  }

  void _submit() {
    final v = _text.text.replaceAll(RegExp(r'\D'), '');
    if (v.length == 6) widget.controller.submit(v);
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    final name = c.peerName ?? widget.initialName;
    return AlertDialog(
      icon: const Icon(Icons.link_rounded, size: 40),
      title: Text('Appairage avec $name'),
      content: SizedBox(
        width: 380,
        child: c.waiting
            ? const Column(mainAxisSize: MainAxisSize.min, children: [
                SizedBox(height: 8),
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('Connexion sécurisée en cours…', textAlign: TextAlign.center),
              ])
            : Column(mainAxisSize: MainAxisSize.min, children: [
                Text('Un code à 6 chiffres s\'affiche sur « $name ». Saisissez-le ici :', textAlign: TextAlign.center),
                const SizedBox(height: 16),
                TextField(
                  controller: _text,
                  autofocus: true,
                  keyboardType: TextInputType.number,
                  textAlign: TextAlign.center,
                  maxLength: 6,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(letterSpacing: 8, fontWeight: FontWeight.w600),
                  decoration: InputDecoration(
                    counterText: '',
                    hintText: '______',
                    hintStyle: TextStyle(color: Theme.of(context).colorScheme.outlineVariant),
                    errorText: c.error,
                    errorMaxLines: 3,
                    border: const OutlineInputBorder(),
                  ),
                  onChanged: (v) {
                    if (v.length == 6) _submit();
                  },
                  onSubmitted: (_) => _submit(),
                ),
              ]),
      ),
      actions: [
        TextButton(onPressed: () => c.close(), child: const Text('Annuler')),
        if (!c.waiting) FilledButton(onPressed: _submit, child: const Text('Valider')),
      ],
    );
  }
}
