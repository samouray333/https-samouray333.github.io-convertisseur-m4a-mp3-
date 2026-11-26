// Tri automatique des fichiers reçus.
//
// Un fichier seul est rangé selon son type (Photos, Vidéos, Musique…).
// Un dossier envoyé en entier garde son arborescence telle quelle, pour ne
// pas éparpiller son contenu.
import 'package:path/path.dart' as p;

enum SortMode {
  none, // tout dans le dossier de réception
  type, // Photos / Vidéos / Musique / Documents…
  typeDevice, // <Appareil>/Photos, <Appareil>/Vidéos…
}

SortMode sortModeFromString(String? s) =>
    SortMode.values.firstWhere((e) => e.name == s, orElse: () => SortMode.type);

extension SortModeFr on SortMode {
  String get label => switch (this) {
        SortMode.none => 'Aucun tri',
        SortMode.type => 'Par type',
        SortMode.typeDevice => 'Par appareil puis par type',
      };

  String get example {
    String j(List<String> parts) => parts.join(p.separator);
    return switch (this) {
      SortMode.none => 'Tout arrive directement dans le dossier de réception.',
      SortMode.type => '${j(['Transferys', 'Photos'])}, ${j(['Transferys', 'Vidéos'])}, ${j(['Transferys', 'Documents'])}…',
      SortMode.typeDevice => '${j(['Transferys', 'Tel Quentin', 'Photos'])}, ${j(['Transferys', 'PC Bureau', 'Documents'])}…',
    };
  }
}

const _images = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif', '.bmp', '.tif', '.tiff', '.svg', '.raw', '.dng', '.cr2', '.nef', '.arw'};
const _videos = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v', '.3gp', '.wmv', '.flv', '.mts', '.m2ts', '.mpg', '.mpeg'};
const _audio = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma', '.aiff', '.aif', '.mid', '.midi', '.amr'};
const _docs = {
  '.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt', '.md', '.xls', '.xlsx', '.ods', '.csv', '.ppt', '.pptx', '.odp', //
  '.epub', '.pages', '.numbers', '.key', '.json', '.xml', '.html', '.htm',
};
const _archives = {'.zip', '.rar', '.7z', '.tar', '.gz', '.xz', '.bz2', '.iso'};
const _apps = {'.apk', '.aab', '.xapk', '.exe', '.msi', '.msix', '.appx', '.bat', '.cmd', '.ps1'};

/// Catégorie d'un fichier d'après son extension.
String categoryFor(String fileName) {
  final ext = p.extension(fileName).toLowerCase();
  if (_images.contains(ext)) return 'Photos';
  if (_videos.contains(ext)) return 'Vidéos';
  if (_audio.contains(ext)) return 'Musique';
  if (_docs.contains(ext)) return 'Documents';
  if (_archives.contains(ext)) return 'Archives';
  if (_apps.contains(ext)) return 'Applications';
  return 'Autres';
}

/// Dossiers à ajouter devant le chemin relatif d'un fichier reçu.
/// [parts] est le chemin relatif déjà nettoyé (composants).
List<String> sortedParts(List<String> parts, SortMode mode, String deviceFolder) {
  if (mode == SortMode.none) return parts;
  final prefix = <String>[if (mode == SortMode.typeDevice) deviceFolder];
  // Dossier envoyé en entier : on garde son arborescence.
  if (parts.length > 1) return [...prefix, ...parts];
  return [...prefix, categoryFor(parts.last), ...parts];
}
