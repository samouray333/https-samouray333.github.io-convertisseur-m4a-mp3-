// Lecture directe d'un descripteur de fichier natif (Android) via la libc.
//
// Pourquoi : rouvrir « /proc/self/fd/N » repasse par le chemin du fichier,
// et Android 11+ refuse cet accès pour les médias d'autres applis (vidéos
// WhatsApp, photos de la galerie…). On lit donc le descripteur que le
// système nous a confié, avec pread(), sans copie ni rouverture.
import 'dart:ffi';
import 'dart:io';
import 'dart:typed_data';

import 'package:ffi/ffi.dart';

import 'file_source.dart';

typedef _PreadC = IntPtr Function(Int32 fd, Pointer<Uint8> buf, IntPtr count, Int64 offset);
typedef _PreadD = int Function(int fd, Pointer<Uint8> buf, int count, int offset);
typedef _ReadC = IntPtr Function(Int32 fd, Pointer<Uint8> buf, IntPtr count);
typedef _ReadD = int Function(int fd, Pointer<Uint8> buf, int count);
typedef _CloseC = Int32 Function(Int32 fd);
typedef _CloseD = int Function(int fd);

class FdReader implements SourceReader {
  FdReader(this.fd);
  final int fd;
  int _pos = 0;
  int _seqPos = 0; // position réelle du curseur pour read() (tubes)
  bool _closed = false;
  static const int _bufSize = 1 << 20;
  Pointer<Uint8>? _buf;

  static final DynamicLibrary _libc = Platform.isAndroid ? DynamicLibrary.open('libc.so') : DynamicLibrary.process();
  static final _PreadD _pread = _libc.lookupFunction<_PreadC, _PreadD>('pread64');
  static final _ReadD _read = _libc.lookupFunction<_ReadC, _ReadD>('read');
  static final _CloseD _close = _libc.lookupFunction<_CloseC, _CloseD>('close');

  @override
  Future<void> setPosition(int position) async => _pos = position;

  @override
  Future<Uint8List> read(int count) async {
    if (_closed) throw const FileSystemException('Fichier déjà fermé');
    final buf = _buf ??= malloc<Uint8>(_bufSize);
    final out = Uint8List(count);
    var got = 0;
    while (got < count) {
      final want = count - got < _bufSize ? count - got : _bufSize;
      var n = _pread(fd, buf, want, _pos);
      if (n < 0) {
        // Descripteur non positionnable (tube d'un fournisseur cloud) :
        // lecture séquentielle, possible seulement si on suit le curseur.
        if (_pos != _seqPos) {
          throw FileSystemException('Lecture impossible à la position $_pos (fichier non repositionnable)');
        }
        n = _read(fd, buf, want);
        if (n < 0) throw const FileSystemException('Lecture du fichier refusée par Android');
        _seqPos += n;
      }
      if (n == 0) break; // fin de fichier
      out.setRange(got, got + n, buf.asTypedList(n));
      got += n;
      _pos += n;
    }
    return got == count ? out : Uint8List.sublistView(out, 0, got);
  }

  @override
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _close(fd);
    final b = _buf;
    if (b != null) malloc.free(b);
    _buf = null;
  }
}
