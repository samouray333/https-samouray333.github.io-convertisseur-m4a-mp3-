// Formatage en français : tailles, vitesses, durées, dates.

String formatSize(int bytes) {
  if (bytes < 1024) return '$bytes o';
  const units = ['Ko', 'Mo', 'Go', 'To'];
  double v = bytes / 1024;
  int i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  final s = v >= 100 ? v.toStringAsFixed(0) : (v >= 10 ? v.toStringAsFixed(1) : v.toStringAsFixed(2));
  return '${s.replaceAll('.', ',')} ${units[i]}';
}

String formatSpeed(double bytesPerSecond) {
  final mo = bytesPerSecond / (1024 * 1024);
  if (mo >= 1) return '${mo.toStringAsFixed(1).replaceAll('.', ',')} Mo/s';
  return '${(bytesPerSecond / 1024).toStringAsFixed(0)} Ko/s';
}

String formatDuration(Duration d) {
  if (d.inSeconds < 1) return 'moins d\'une seconde';
  final h = d.inHours, m = d.inMinutes % 60, s = d.inSeconds % 60;
  if (h > 0) return '$h h ${m.toString().padLeft(2, '0')} min';
  if (m > 0) return '$m min ${s.toString().padLeft(2, '0')} s';
  return '$s s';
}

String formatDate(DateTime d) {
  String two(int v) => v.toString().padLeft(2, '0');
  return '${two(d.day)}/${two(d.month)}/${d.year} à ${two(d.hour)}:${two(d.minute)}';
}
