// Aide au dépannage de la connexion.
import 'package:flutter/material.dart';

class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key});

  @override
  Widget build(BuildContext context) {
    const items = [
      (
        Icons.wifi_rounded,
        'Même réseau Wi-Fi',
        'Les deux appareils doivent être sur le même Wi-Fi (même box). Les réseaux « invités » isolent souvent les appareils entre eux : utilisez le réseau principal. Sans box, activez le point d\'accès du téléphone et connectez-y le PC.'
      ),
      (
        Icons.shield_outlined,
        'Le pare-feu Windows bloque Transferys',
        'Si le téléphone voit le PC mais ne peut pas s\'y connecter : Démarrer > « Autoriser une application via le Pare-feu Windows » > Modifier les paramètres > cochez Transferys pour « Privé ». L\'installateur ajoute normalement cette autorisation tout seul. Vérifiez aussi que votre Wi-Fi est déclaré en réseau « Privé » et non « Public ».'
      ),
      (
        Icons.qr_code_2_rounded,
        'L\'appareil n\'apparaît pas',
        'La détection automatique peut être bloquée par certains routeurs. Utilisez Ajouter > QR code (affiché sur le PC, scanné par le téléphone) ou saisissez l\'adresse IP indiquée en haut de l\'écran de l\'autre appareil.'
      ),
      (
        Icons.battery_alert_outlined,
        'Le transfert s\'arrête quand le téléphone se met en veille',
        'Transferys utilise un service au premier plan (notification « Transfert en cours »). Si votre téléphone (Xiaomi, Huawei, Samsung…) le coupe quand même, allez dans Réglages > Ne pas limiter la batterie.'
      ),
      (
        Icons.restart_alt_rounded,
        'Coupure en plein transfert',
        'Pas de panique : Transferys réessaie automatiquement pendant 10 minutes et reprend là où il s\'était arrêté. Même si l\'appli a été fermée, renvoyez les mêmes fichiers : la partie déjà reçue est conservée 7 jours.'
      ),
      (
        Icons.sd_storage_outlined,
        'Espace disque insuffisant',
        'L\'espace libre est vérifié avant de commencer. Libérez de la place ou choisissez un autre dossier de réception dans les réglages.'
      ),
      (
        Icons.gpp_maybe_outlined,
        'Code incorrect / identité changée',
        'Si Transferys a été réinstallé sur un appareil, son certificat de sécurité change : retirez-le des appareils de confiance (des deux côtés) puis appairez-les à nouveau.'
      ),
    ];
    return Scaffold(
      appBar: AppBar(title: const Text('Aide')),
      body: ListView(padding: const EdgeInsets.all(16), children: [
        for (final it in items)
          Card(
            child: ListTile(
              contentPadding: const EdgeInsets.all(14),
              leading: Icon(it.$1, size: 30, color: Theme.of(context).colorScheme.primary),
              title: Padding(padding: const EdgeInsets.only(bottom: 6), child: Text(it.$2, style: Theme.of(context).textTheme.titleMedium)),
              subtitle: Text(it.$3),
            ),
          ),
      ]),
    );
  }
}
