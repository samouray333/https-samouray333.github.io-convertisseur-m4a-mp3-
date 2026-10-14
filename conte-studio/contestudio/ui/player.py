"""Lecteur audio intégré (lecture en flux via PortAudio) et barre de lecture."""

from __future__ import annotations

import logging
import tempfile
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from .. import paths
from . import icons, theme
from .widgets import IconButton, label

log = logging.getLogger(__name__)


class AudioPlayer(QObject):
    state_changed = Signal(str)  # playing | paused | stopped
    error = Signal(str)

    def __init__(self):
        super().__init__()
        self._file: sf.SoundFile | None = None
        self._stream = None
        self._lock = threading.Lock()
        self._frames_played = 0
        self._total = 0
        self._sr = 44100
        self._channels = 1
        self._volume = 0.9
        self._state = "stopped"
        self._finished_flag = False
        self._paused = False
        self.path: Path | None = None
        self.title = ""
        self._end_at: int | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(80)

    # -- chargement --------------------------------------------------------------------
    def _open(self, path: Path) -> sf.SoundFile:
        try:
            return sf.SoundFile(str(path))
        except Exception:
            from ..core import ffmpeg

            tmp = Path(tempfile.mkdtemp(dir=paths.temp_dir())) / "lecture.wav"
            ffmpeg.decode_to_wav(path, tmp, sample_rate=44100, mono=False)
            return sf.SoundFile(str(tmp))

    def play_file(self, path: str | Path, title: str = "", start: float = 0.0, end: float | None = None) -> None:
        self.stop()
        try:
            f = self._open(Path(path))
        except Exception as exc:
            self.error.emit(f"Lecture impossible : {exc}")
            return
        with self._lock:
            self._file = f
            self._sr = f.samplerate
            self._channels = min(2, f.channels)
            self._total = f.frames
            start_frame = int(max(0.0, start) * self._sr)
            f.seek(min(start_frame, max(0, self._total - 1)))
            self._frames_played = start_frame
            self._end_at = int(end * self._sr) if end is not None else None
        self.path = Path(path)
        self.title = title or Path(path).stem
        self._start_stream()

    def _start_stream(self) -> None:
        try:
            import sounddevice as sd
        except Exception as exc:  # PortAudio absent
            self.error.emit(f"Aucune sortie audio disponible ({exc}).")
            return
        try:
            self._stream = sd.OutputStream(samplerate=self._sr, channels=self._channels, dtype="float32",
                                           callback=self._callback, blocksize=2048)
            self._paused = False
            self._stream.start()
            self._set_state("playing")
        except Exception as exc:
            self._stream = None
            self.error.emit(f"Impossible d'ouvrir la sortie audio : {exc}")

    def _callback(self, outdata, frames, time_info, status):  # thread audio
        import sounddevice as sd

        with self._lock:
            f = self._file
            if f is None:
                outdata.fill(0)
                raise sd.CallbackStop()
            if self._paused:
                outdata.fill(0)
                return
            want = frames
            if self._end_at is not None:
                want = max(0, min(frames, self._end_at - self._frames_played))
            data = f.read(want, dtype="float32", always_2d=True) if want > 0 else np.zeros((0, f.channels), "float32")
            n = len(data)
            if data.shape[1] != self._channels:
                data = data[:, : self._channels] if data.shape[1] > self._channels else np.repeat(data, self._channels, 1)
            outdata[:n] = data * self._volume
            if n < frames:
                outdata[n:] = 0
            self._frames_played += n
            if n < frames:
                self._finished_flag = True
                raise sd.CallbackStop()

    def _poll(self) -> None:
        if self._finished_flag:
            self._finished_flag = False
            self._close_stream()
            self._set_state("stopped")

    def _set_state(self, s: str) -> None:
        if s != self._state:
            self._state = s
            self.state_changed.emit(s)

    # -- commandes ---------------------------------------------------------------------
    @property
    def state(self) -> str:
        return self._state

    def toggle(self) -> None:
        if self._state == "playing":
            self.pause()
        elif self._state == "paused":
            self.resume()
        elif self.path is not None:
            self.play_file(self.path, self.title)

    def pause(self) -> None:
        if self._stream is not None and self._state == "playing":
            self._paused = True
            self._set_state("paused")

    def resume(self) -> None:
        if self._stream is not None and self._state == "paused":
            self._paused = False
            self._set_state("playing")

    def _close_stream(self) -> None:
        st = self._stream
        self._stream = None
        if st is not None:
            try:
                st.stop()
                st.close()
            except Exception:
                pass

    def stop(self) -> None:
        self._close_stream()
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except Exception:
                    pass
            self._file = None
        self._finished_flag = False
        self._set_state("stopped")

    def seek(self, seconds: float) -> None:
        with self._lock:
            if self._file is None:
                return
            frame = int(max(0, min(self._total - 1, seconds * self._sr)))
            self._file.seek(frame)
            self._frames_played = frame

    def set_volume(self, v: float) -> None:
        self._volume = max(0.0, min(1.0, v))

    def position(self) -> float:
        return self._frames_played / float(self._sr or 1)

    def duration(self) -> float:
        return self._total / float(self._sr or 1)


def fmt_time(t: float) -> str:
    t = max(0, int(t))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class PlayerBar(QFrame):
    def __init__(self, player: AudioPlayer):
        super().__init__()
        self.setObjectName("PlayerBar")
        self.player = player
        self.setFixedHeight(70)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 10, 20, 10)
        lay.setSpacing(14)

        self.back = IconButton("skip-back", "Reculer de 10 s", 34, 16)
        self.back.clicked.connect(lambda: self.player.seek(self.player.position() - 10))
        self.play = IconButton("play", "Lecture / pause (Espace)", 44, 18, color="#FFFFFF", obj="PlayBig")
        self.play.clicked.connect(self.player.toggle)
        self.fwd = IconButton("skip-fwd", "Avancer de 10 s", 34, 16)
        self.fwd.clicked.connect(lambda: self.player.seek(self.player.position() + 10))
        lay.addWidget(self.back)
        lay.addWidget(self.play)
        lay.addWidget(self.fwd)

        col = QVBoxLayout()
        col.setSpacing(4)
        top = QHBoxLayout()
        self.title = label("Rien en lecture", "Muted")
        self.time = label("0:00 / 0:00", "Faint")
        top.addWidget(self.title, 1)
        top.addWidget(self.time)
        col.addLayout(top)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderReleased.connect(self._seek)
        col.addLayout(_wrap(self.slider))
        lay.addLayout(col, 1)

        vol_icon = QLabel()
        vol_icon.setPixmap(icons.pixmap("volume", theme.CURRENT.muted, 18))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setFixedWidth(110)
        self.volume.setRange(0, 100)
        from ..config import settings

        self.volume.setValue(int(float(settings().get("player_volume", 0.9)) * 100))
        self.player.set_volume(self.volume.value() / 100)
        self.volume.valueChanged.connect(self._volume)
        lay.addWidget(vol_icon)
        lay.addWidget(self.volume)

        self.player.state_changed.connect(self._state)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(120)

    def _volume(self, v: int) -> None:
        self.player.set_volume(v / 100)
        from ..config import settings

        settings().set("player_volume", v / 100)

    def _seek(self) -> None:
        d = self.player.duration()
        if d > 0:
            self.player.seek(self.slider.value() / 1000 * d)

    def _state(self, s: str) -> None:
        self.play.set_icon_name("pause" if s == "playing" else "play", "#FFFFFF")
        if self.player.path is not None:
            self.title.setText(self.player.title)
            self.title.setObjectName("" if s == "playing" else "Muted")
            self.title.setStyleSheet("font-weight: 600;" if s == "playing" else "")

    def _tick(self) -> None:
        d = self.player.duration()
        pos = self.player.position()
        if not self.slider.isSliderDown() and d > 0:
            self.slider.setValue(int(pos / d * 1000))
        self.time.setText(f"{fmt_time(pos)} / {fmt_time(d)}")


def _wrap(w: QWidget) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(w)
    return lay
