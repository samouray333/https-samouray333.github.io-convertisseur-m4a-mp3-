// Identité visuelle de Transferys 2.0 : palette, typographie, thèmes.
//
// Palette : bleu nuit (texte), bleu Transferys (action), lagon (signal),
// brume (fond clair). Mode sombre en bleu nuit profond, pas en gris-noir.
// Typographie : Manrope, une seule famille (fichiers intégrés à l'appli).
import 'package:flutter/material.dart';

const brandBlue = Color(0xFF2F6BFF);
const brandCyan = Color(0xFF00B5C8);
const ink = Color(0xFF14213D);
const mist = Color(0xFFEEF3FB);
const nightBg = Color(0xFF0E1626);
const nightSurface = Color(0xFF16213A);
const okGreen = Color(0xFF1E9E6A);
const warnAmber = Color(0xFFD98A0B);
const errRed = Color(0xFFD64545);

const _font = 'Manrope';

/// Rayons : grands pour les zones, moyens pour les éléments, petits pour les puces.
class Radii {
  static const zone = 24.0;
  static const item = 16.0;
  static const chip = 10.0;
}

ColorScheme _scheme(Brightness b) {
  final base = ColorScheme.fromSeed(seedColor: brandBlue, brightness: b);
  if (b == Brightness.light) {
    return base.copyWith(
      primary: brandBlue,
      onPrimary: Colors.white,
      primaryContainer: const Color(0xFFDCE6FF),
      onPrimaryContainer: const Color(0xFF0B2A80),
      secondary: brandCyan,
      onSecondary: Colors.white,
      secondaryContainer: const Color(0xFFD3F4F8),
      onSecondaryContainer: const Color(0xFF00434B),
      surface: Colors.white,
      onSurface: ink,
      onSurfaceVariant: const Color(0xFF55607A),
      surfaceContainerLowest: Colors.white,
      surfaceContainerLow: const Color(0xFFF6F8FD),
      surfaceContainer: mist,
      surfaceContainerHigh: const Color(0xFFE4EBF7),
      surfaceContainerHighest: const Color(0xFFDAE3F2),
      outline: const Color(0xFF8C97AE),
      outlineVariant: const Color(0xFFD5DDEA),
      error: errRed,
    );
  }
  return base.copyWith(
    primary: const Color(0xFF6B95FF),
    onPrimary: const Color(0xFF041B57),
    primaryContainer: const Color(0xFF1C3C9E),
    onPrimaryContainer: const Color(0xFFDCE6FF),
    secondary: const Color(0xFF3FD3E3),
    onSecondary: const Color(0xFF00363C),
    secondaryContainer: const Color(0xFF0D4D57),
    onSecondaryContainer: const Color(0xFFC9F5FA),
    surface: nightBg,
    onSurface: const Color(0xFFE6ECF7),
    onSurfaceVariant: const Color(0xFFA3AEC4),
    surfaceContainerLowest: const Color(0xFF0A111E),
    surfaceContainerLow: const Color(0xFF131D31),
    surfaceContainer: nightSurface,
    surfaceContainerHigh: const Color(0xFF1D2A45),
    surfaceContainerHighest: const Color(0xFF253453),
    outline: const Color(0xFF6E7A94),
    outlineVariant: const Color(0xFF2B3958),
    error: const Color(0xFFFF8A80),
  );
}

TextTheme _text(TextTheme t, Color c) {
  TextStyle s(TextStyle? x, double size, FontWeight w, {double ls = 0, double h = 1.3}) =>
      (x ?? const TextStyle()).copyWith(fontFamily: _font, fontSize: size, fontWeight: w, letterSpacing: ls, height: h, color: c);
  return t.copyWith(
    displayLarge: s(t.displayLarge, 48, FontWeight.w800, ls: -1.2, h: 1.05),
    displayMedium: s(t.displayMedium, 40, FontWeight.w800, ls: -0.8, h: 1.1),
    displaySmall: s(t.displaySmall, 32, FontWeight.w800, ls: -0.6, h: 1.15),
    headlineLarge: s(t.headlineLarge, 28, FontWeight.w800, ls: -0.5, h: 1.2),
    headlineMedium: s(t.headlineMedium, 24, FontWeight.w800, ls: -0.4, h: 1.2),
    headlineSmall: s(t.headlineSmall, 21, FontWeight.w700, ls: -0.3, h: 1.25),
    titleLarge: s(t.titleLarge, 19, FontWeight.w700, ls: -0.2),
    titleMedium: s(t.titleMedium, 16, FontWeight.w700, ls: -0.1),
    titleSmall: s(t.titleSmall, 14, FontWeight.w700),
    bodyLarge: s(t.bodyLarge, 16, FontWeight.w500, h: 1.5),
    bodyMedium: s(t.bodyMedium, 14, FontWeight.w500, h: 1.45),
    bodySmall: s(t.bodySmall, 12.5, FontWeight.w500, h: 1.4),
    labelLarge: s(t.labelLarge, 14, FontWeight.w700, ls: 0.1),
    labelMedium: s(t.labelMedium, 12.5, FontWeight.w700, ls: 0.1),
    labelSmall: s(t.labelSmall, 11.5, FontWeight.w700, ls: 0.2),
  );
}

ThemeData buildTheme(Brightness b) {
  final cs = _scheme(b);
  final base = ThemeData(useMaterial3: true, colorScheme: cs, brightness: b, fontFamily: _font);
  final text = _text(base.textTheme, cs.onSurface);
  final light = b == Brightness.light;
  final bg = light ? mist : nightBg;
  final panel = light ? Colors.white : nightSurface;
  final navBg = light ? Colors.white : const Color(0xFF111B2E);
  return base.copyWith(
    scaffoldBackgroundColor: bg,
    textTheme: text,
    cardTheme: CardThemeData(
      elevation: 0,
      color: panel,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.item)),
      margin: const EdgeInsets.only(bottom: 10),
    ),
    appBarTheme: AppBarTheme(
      centerTitle: false,
      backgroundColor: bg,
      surfaceTintColor: Colors.transparent,
      scrolledUnderElevation: 0,
      elevation: 0,
      titleTextStyle: text.titleLarge,
      foregroundColor: cs.onSurface,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: navBg,
      surfaceTintColor: Colors.transparent,
      indicatorColor: cs.primary.withValues(alpha: 0.14),
      elevation: 0,
      height: 68,
      labelTextStyle: WidgetStateProperty.resolveWith((s) => text.labelSmall!.copyWith(
            color: s.contains(WidgetState.selected) ? cs.primary : cs.onSurfaceVariant,
          )),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
            color: s.contains(WidgetState.selected) ? cs.primary : cs.onSurfaceVariant,
          )),
    ),
    navigationRailTheme: NavigationRailThemeData(
      backgroundColor: navBg,
      indicatorColor: cs.primary.withValues(alpha: 0.14),
      selectedIconTheme: IconThemeData(color: cs.primary),
      unselectedIconTheme: IconThemeData(color: cs.onSurfaceVariant),
      selectedLabelTextStyle: text.labelMedium!.copyWith(color: cs.primary),
      unselectedLabelTextStyle: text.labelMedium!.copyWith(color: cs.onSurfaceVariant),
    ),
    dividerTheme: DividerThemeData(color: cs.outlineVariant, thickness: 1, space: 1),
    listTileTheme: ListTileThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.item)),
      titleTextStyle: text.titleMedium,
      subtitleTextStyle: text.bodySmall!.copyWith(color: cs.onSurfaceVariant),
      iconColor: cs.onSurfaceVariant,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: panel,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.zone)),
      titleTextStyle: text.headlineSmall,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: light ? ink : const Color(0xFFE6ECF7),
      contentTextStyle: text.bodyMedium!.copyWith(color: light ? Colors.white : ink),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.chip + 2)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.item)),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        textStyle: text.labelLarge,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.item)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        side: BorderSide(color: cs.outlineVariant, width: 1.5),
        textStyle: text.labelLarge,
      ),
    ),
    textButtonTheme: TextButtonThemeData(style: TextButton.styleFrom(textStyle: text.labelLarge)),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: panel,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(Radii.item), borderSide: BorderSide(color: cs.outlineVariant)),
      enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(Radii.item), borderSide: BorderSide(color: cs.outlineVariant)),
      focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(Radii.item), borderSide: BorderSide(color: cs.primary, width: 2)),
    ),
    switchTheme: SwitchThemeData(
      trackOutlineColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? Colors.transparent : cs.outlineVariant),
    ),
    chipTheme: ChipThemeData(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.chip)),
      side: BorderSide(color: cs.outlineVariant),
      labelStyle: text.labelMedium,
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.item)),
        side: BorderSide(color: cs.outlineVariant),
        selectedBackgroundColor: cs.primary.withValues(alpha: 0.14),
        selectedForegroundColor: cs.primary,
        textStyle: text.labelMedium,
      ),
    ),
    progressIndicatorTheme: ProgressIndicatorThemeData(
      color: cs.primary,
      linearTrackColor: cs.outlineVariant.withValues(alpha: 0.6),
      circularTrackColor: cs.outlineVariant.withValues(alpha: 0.6),
    ),
    tooltipTheme: TooltipThemeData(
      decoration: BoxDecoration(color: ink.withValues(alpha: 0.92), borderRadius: BorderRadius.circular(8)),
      textStyle: text.bodySmall!.copyWith(color: Colors.white),
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

/// Zone de contenu (blanc / bleu nuit) à grand rayon : regroupe une section.
class Zone extends StatelessWidget {
  const Zone({super.key, required this.child, this.padding = const EdgeInsets.all(16), this.margin = const EdgeInsets.only(bottom: 14)});
  final Widget child;
  final EdgeInsets padding;
  final EdgeInsets margin;
  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      margin: margin,
      padding: padding,
      decoration: BoxDecoration(color: dark ? nightSurface : Colors.white, borderRadius: BorderRadius.circular(Radii.zone)),
      child: child,
    );
  }
}
