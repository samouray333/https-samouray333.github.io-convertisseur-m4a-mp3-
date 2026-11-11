// Identité visuelle : couleurs, thèmes clair / sombre, logo.
import 'package:flutter/material.dart';

const brandBlue = Color(0xFF2F6BFF);
const brandCyan = Color(0xFF00BCD4);

ThemeData buildTheme(Brightness b) {
  final cs = ColorScheme.fromSeed(
    seedColor: brandBlue,
    brightness: b,
    dynamicSchemeVariant: DynamicSchemeVariant.fidelity,
  );
  return ThemeData(
    useMaterial3: true,
    colorScheme: cs,
    brightness: b,
    visualDensity: VisualDensity.standard,
    cardTheme: CardThemeData(
      elevation: 0,
      color: b == Brightness.light ? cs.surfaceContainerLow : cs.surfaceContainer,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      margin: const EdgeInsets.only(bottom: 10),
    ),
    appBarTheme: AppBarTheme(centerTitle: false, backgroundColor: cs.surface, scrolledUnderElevation: 1),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
    ),
  );
}

class BrandLogo extends StatelessWidget {
  const BrandLogo({super.key, this.size = 40});
  final double size;
  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(size * 0.22),
        child: Image.asset('assets/logo.png', width: size, height: size, filterQuality: FilterQuality.medium),
      );
}
