// Calcul SHA-256 incrémental. Pour les gros fichiers, le hachage tourne dans
// un isolate séparé (autre cœur du processeur) afin de ne pas ralentir le
// réseau ; une contre-pression limite la mémoire en attente à 64 Mo.
import 'dart:async';
import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

class _Acc implements Sink<Digest> {
  Digest? value;
  @override
  void add(Digest data) => value = data;
  @override
  void close() {}
}

abstract class StreamingHasher {
  /// Fichiers au-delà de ce seuil : hachage en arrière-plan.
  static const int isolateThreshold = 16 * 1024 * 1024;

  static Future<StreamingHasher> create(int expectedSize) async {
    if (expectedSize < isolateThreshold) return InlineHasher();
    try {
      return await IsolateHasher.spawn();
    } catch (_) {
      return InlineHasher();
    }
  }

  /// Ajoute des données (attend si trop de données sont en file).
  Future<void> add(Uint8List data);

  /// Termine et renvoie le SHA-256 hexadécimal.
  Future<String> close();

  /// Abandonne sans résultat.
  void dispose();
}

class InlineHasher extends StreamingHasher {
  final _acc = _Acc();
  late final ByteConversionSink _sink = sha256.startChunkedConversion(_acc);
  @override
  Future<void> add(Uint8List data) async => _sink.add(data);
  @override
  Future<String> close() async {
    _sink.close();
    return _acc.value.toString();
  }

  @override
  void dispose() {}
}

class IsolateHasher extends StreamingHasher {
  IsolateHasher._(this._isolate, this._toWorker, this._fromWorker, this._events);

  final Isolate _isolate;
  final SendPort _toWorker;
  final ReceivePort _fromWorker;
  final StreamIterator<dynamic> _events;
  int _pending = 0;
  static const int _maxPending = 64 * 1024 * 1024;
  final _waiters = <Completer<void>>[];
  Completer<String>? _done;

  static Future<IsolateHasher> spawn() async {
    final rp = ReceivePort();
    final iso = await Isolate.spawn(_worker, rp.sendPort, errorsAreFatal: true);
    final it = StreamIterator<dynamic>(rp);
    await it.moveNext();
    final sp = it.current as SendPort;
    final h = IsolateHasher._(iso, sp, rp, it);
    h._listen();
    return h;
  }

  Future<void> _listen() async {
    while (await _events.moveNext()) {
      final m = _events.current;
      if (m is int) {
        _pending -= m;
        while (_pending < _maxPending && _waiters.isNotEmpty) {
          _waiters.removeAt(0).complete();
        }
      } else if (m is String) {
        _done?.complete(m);
        break;
      }
    }
  }

  @override
  Future<void> add(Uint8List data) async {
    if (data.isEmpty) return;
    _pending += data.length;
    _toWorker.send(TransferableTypedData.fromList([data]));
    if (_pending >= _maxPending) {
      final c = Completer<void>();
      _waiters.add(c);
      await c.future;
    }
  }

  @override
  Future<String> close() async {
    _done = Completer<String>();
    _toWorker.send(null);
    final d = await _done!.future;
    _cleanup();
    return d;
  }

  @override
  void dispose() => _cleanup();

  void _cleanup() {
    _fromWorker.close();
    _isolate.kill(priority: Isolate.immediate);
    for (final w in _waiters) {
      if (!w.isCompleted) w.complete();
    }
    _waiters.clear();
  }

  static void _worker(SendPort out) {
    final inbox = ReceivePort();
    out.send(inbox.sendPort);
    final acc = _Acc();
    final sink = sha256.startChunkedConversion(acc);
    inbox.listen((m) {
      if (m is TransferableTypedData) {
        final b = m.materialize().asUint8List();
        sink.add(b);
        out.send(b.length);
      } else {
        sink.close();
        out.send(acc.value.toString());
        inbox.close();
      }
    });
  }
}
