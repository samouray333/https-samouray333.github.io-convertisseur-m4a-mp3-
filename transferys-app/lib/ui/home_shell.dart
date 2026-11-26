// Structure principale : navigation entre Envoyer, Transferts, Historique,
// Réglages (barre du bas sur téléphone, rail latéral sur PC).
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_state.dart';
import 'brand.dart';
import 'screens/browse_screen.dart';
import 'screens/history_screen.dart';
import 'screens/send_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/transfers_screen.dart';

class HomeShell extends StatelessWidget {
  const HomeShell({super.key});

  static const _titles = ['Envoyer', 'Transferts', 'Parcourir', 'Historique', 'Réglages'];

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final active = app.activeJobs.length;
    final pages = const [SendScreen(), TransfersScreen(), BrowseScreen(), HistoryScreen(), SettingsScreen()];
    Widget badge(Widget icon) => active > 0 ? Badge(label: Text('$active'), child: icon) : icon;
    final wide = MediaQuery.sizeOf(context).width >= 760;

    // Les onglets cachés ne font tourner aucune animation.
    final body = IndexedStack(index: app.tab, children: [
      for (var i = 0; i < pages.length; i++) TickerMode(enabled: i == app.tab, child: pages[i]),
    ]);
    final appBar = AppBar(
      toolbarHeight: 60,
      title: Row(children: [
        const BrandLogo(size: 30),
        const SizedBox(width: 10),
        Text(app.tab == 0 ? 'Transferys' : _titles[app.tab]),
      ]),
    );

    if (wide) {
      return Scaffold(
        body: SafeArea(
          child: Row(children: [
          NavigationRail(
            selectedIndex: app.tab,
            onDestinationSelected: app.setTab,
            labelType: NavigationRailLabelType.all,
            minWidth: 92,
            groupAlignment: -0.85,
            leading: const Padding(
              padding: EdgeInsets.only(top: 18, bottom: 26),
              child: Tooltip(message: 'Transferys', child: BrandLogo(size: 42)),
            ),
            destinations: [
              const NavigationRailDestination(icon: Icon(Icons.send_outlined), selectedIcon: Icon(Icons.send_rounded), label: Text('Envoyer')),
              NavigationRailDestination(icon: badge(const Icon(Icons.swap_vert_rounded)), label: const Text('Transferts')),
              const NavigationRailDestination(icon: Icon(Icons.folder_open_outlined), selectedIcon: Icon(Icons.folder_open_rounded), label: Text('Parcourir')),
              const NavigationRailDestination(icon: Icon(Icons.history_rounded), label: Text('Historique')),
              const NavigationRailDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings_rounded), label: Text('Réglages')),
            ],
          ),
          Expanded(
            child: Align(
              alignment: Alignment.topCenter,
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: app.tab == 0 ? 1180 : 920),
                child: app.tab == 0
                    ? body
                    : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                        Padding(
                          padding: const EdgeInsets.fromLTRB(26, 26, 26, 6),
                          child: Text(_titles[app.tab], style: Theme.of(context).textTheme.headlineMedium),
                        ),
                        Expanded(child: body),
                      ]),
              ),
            ),
          ),
        ]),
        ),
      );
    }
    return Scaffold(
      appBar: appBar,
      body: body,
      bottomNavigationBar: NavigationBar(
        selectedIndex: app.tab,
        onDestinationSelected: app.setTab,
        destinations: [
          const NavigationDestination(icon: Icon(Icons.send_outlined), selectedIcon: Icon(Icons.send_rounded), label: 'Envoyer'),
          NavigationDestination(icon: badge(const Icon(Icons.swap_vert_rounded)), label: 'Transferts'),
          const NavigationDestination(icon: Icon(Icons.folder_open_outlined), selectedIcon: Icon(Icons.folder_open_rounded), label: 'Parcourir'),
          const NavigationDestination(icon: Icon(Icons.history_rounded), label: 'Historique'),
          const NavigationDestination(icon: Icon(Icons.settings_outlined), selectedIcon: Icon(Icons.settings_rounded), label: 'Réglages'),
        ],
      ),
    );
  }
}
