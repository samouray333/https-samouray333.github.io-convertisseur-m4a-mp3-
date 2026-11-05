// Extrays : couper des extraits de chansons (Echo Matras)
import { Capacitor } from '@capacitor/core';
import { Filesystem, Directory } from '@capacitor/filesystem';
import { Share } from '@capacitor/share';
import { App } from '@capacitor/app';
import { encodeWav, renderSelection } from './audio.js';

const NATIVE = Capacitor.isNativePlatform();
const FOLDER = 'Extrays';
const HIST_KEY = 'extrays.history.v1';
const PREF_KEY = 'extrays.prefs.v1';
const MIN_SEL = 0.1; // durée minimale d'un extrait (s)

const $ = (id) => document.getElementById(id);

// ---------- État ----------
const S = {
  ctx: null,
  buffer: null,
  fileName: '',
  baseName: '',
  peaks: null, // { lvl: [{block, min, max}] }
  duration: 0,
  selStart: 0,
  selEnd: 0,
  pos: 0,
  viewStart: 0,
  viewDur: 1,
  play: null, // { src, gain, mode, from, to, t0 }
  loop: false,
  fmt: 'mp3-192',
  nameTouched: false,
  busy: false,
};

// ---------- Utilitaires ----------
function fmtTime(t, dec = 1) {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  const sStr = s.toFixed(dec).padStart(dec ? 3 + dec : 2, '0');
  return `${m}:${sStr}`;
}
function parseTime(str) {
  str = String(str).trim().replace(',', '.');
  if (!str) return NaN;
  const parts = str.split(':');
  let t = 0;
  for (const p of parts) {
    const v = parseFloat(p);
    if (isNaN(v)) return NaN;
    t = t * 60 + v;
  }
  return t;
}
function fileStamp(t) {
  const m = Math.floor(t / 60);
  const s = Math.floor(t - m * 60);
  return `${m}m${String(s).padStart(2, '0')}`;
}
function sanitize(name) {
  return name.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_').replace(/\s+/g, ' ').trim().slice(0, 120) || 'extrait';
}
function fmtSize(b) {
  if (b < 1024 * 1024) return `${Math.max(1, Math.round(b / 1024))} Ko`;
  return `${(b / 1024 / 1024).toFixed(1)} Mo`;
}
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function loadJSON(key, def) {
  try { const v = JSON.parse(localStorage.getItem(key)); return v ?? def; } catch { return def; }
}
function saveJSON(key, v) {
  try { localStorage.setItem(key, JSON.stringify(v)); } catch { /* stockage indisponible */ }
}

// ---------- UI de base ----------
let toastTimer = null;
function toast(text, { error = false, action = null, ms = 3500 } = {}) {
  const el = $('toast');
  $('toastText').textContent = text;
  el.classList.toggle('error', error);
  const btn = $('toastAction');
  if (action) {
    btn.hidden = false;
    btn.textContent = action.label;
    btn.onclick = () => { el.hidden = true; action.fn(); };
  } else btn.hidden = true;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, action ? Math.max(ms, 7000) : ms);
}
function busy(on, text = 'Chargement…') {
  S.busy = on;
  $('busyText').textContent = text;
  $('busy').hidden = !on;
}
function showScreen(name) {
  $('home').hidden = name !== 'home';
  $('editor').hidden = name !== 'editor';
  $('btnResume').hidden = !(name === 'home' && S.buffer);
  if (name === 'home') { stopPlayback(); renderHistory(); }
  else requestAnimationFrame(() => { resizeCanvases(); draw(); });
  window.scrollTo(0, 0);
}

// ---------- Chargement ----------
function getCtx() {
  if (!S.ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    S.ctx = new AC({ latencyHint: 'playback' });
  }
  if (S.ctx.state === 'suspended') S.ctx.resume();
  return S.ctx;
}

async function openFile(file) {
  if (!file) return;
  stopPlayback();
  busy(true, 'Lecture de la chanson…');
  try {
    const ctx = getCtx();
    const data = await file.arrayBuffer();
    const buf = await new Promise((res, rej) => {
      const p = ctx.decodeAudioData(data, res, rej);
      if (p && p.catch) p.catch(rej);
    });
    if (!buf || buf.length === 0) throw new Error('vide');
    S.buffer = buf;
    S.fileName = file.name || 'chanson';
    S.baseName = S.fileName.replace(/\.[^.]+$/, '');
    S.duration = buf.duration;
    busy(true, 'Analyse de la forme d’onde…');
    await new Promise((r) => setTimeout(r, 20));
    S.peaks = computePeaks(buf);
    // sélection par défaut : 30 s au milieu, ou toute la chanson si elle est courte
    if (S.duration > 40) {
      S.selStart = Math.floor(S.duration * 0.3);
      S.selEnd = Math.min(S.duration, S.selStart + 30);
    } else { S.selStart = 0; S.selEnd = S.duration; }
    S.pos = S.selStart;
    S.viewStart = 0; S.viewDur = S.duration;
    S.nameTouched = false;
    $('songName').textContent = S.baseName;
    const ch = buf.numberOfChannels > 1 ? 'stéréo' : 'mono';
    $('songMeta').textContent = `${fmtTime(S.duration, 0)} · ${ch} · ${Math.round(buf.sampleRate / 100) / 10} kHz · ${fmtSize(file.size)}`;
    showScreen('editor');
    updateSelUI();
  } catch (e) {
    console.error(e);
    toast('Impossible de lire ce fichier. Format non pris en charge par le téléphone ?', { error: true, ms: 5000 });
  } finally {
    busy(false);
    $('fileInput').value = '';
  }
}

// Pics pré-calculés sur deux niveaux pour un affichage fluide
function computePeaks(buf) {
  const ch0 = buf.getChannelData(0);
  const ch1 = buf.numberOfChannels > 1 ? buf.getChannelData(1) : null;
  const n = buf.length;
  const B1 = 256;
  const n1 = Math.ceil(n / B1);
  const min1 = new Float32Array(n1), max1 = new Float32Array(n1);
  for (let b = 0; b < n1; b++) {
    let mn = 1, mx = -1;
    const end = Math.min(n, (b + 1) * B1);
    for (let i = b * B1; i < end; i++) {
      const v = ch1 ? (ch0[i] + ch1[i]) * 0.5 : ch0[i];
      if (v < mn) mn = v;
      if (v > mx) mx = v;
    }
    min1[b] = mn; max1[b] = mx;
  }
  const F = 16, B2 = B1 * F;
  const n2 = Math.ceil(n1 / F);
  const min2 = new Float32Array(n2), max2 = new Float32Array(n2);
  for (let b = 0; b < n2; b++) {
    let mn = 1, mx = -1;
    const end = Math.min(n1, (b + 1) * F);
    for (let i = b * F; i < end; i++) {
      if (min1[i] < mn) mn = min1[i];
      if (max1[i] > mx) mx = max1[i];
    }
    min2[b] = mn; max2[b] = mx;
  }
  return { lvl: [{ block: B1, min: min1, max: max1 }, { block: B2, min: min2, max: max2 }] };
}

// ---------- Dessin ----------
const wave = $('wave');
const over = $('overview');
let dpr = 1;
function resizeCanvases() {
  dpr = Math.min(3, window.devicePixelRatio || 1);
  for (const c of [wave, over]) {
    const r = c.getBoundingClientRect();
    c.width = Math.max(1, Math.round(r.width * dpr));
    c.height = Math.max(1, Math.round(r.height * dpr));
  }
}

function columnMinMax(t0, t1) {
  const buf = S.buffer, sr = buf.sampleRate;
  let f0 = Math.max(0, Math.floor(t0 * sr));
  let f1 = Math.min(buf.length, Math.ceil(t1 * sr));
  if (f1 <= f0) f1 = Math.min(buf.length, f0 + 1);
  const span = f1 - f0;
  let mn = 1, mx = -1;
  if (span < 256) {
    const c0 = buf.getChannelData(0);
    const c1 = buf.numberOfChannels > 1 ? buf.getChannelData(1) : null;
    for (let i = f0; i < f1; i++) {
      const v = c1 ? (c0[i] + c1[i]) * 0.5 : c0[i];
      if (v < mn) mn = v;
      if (v > mx) mx = v;
    }
  } else {
    const L = span > 256 * 16 * 4 ? S.peaks.lvl[1] : S.peaks.lvl[0];
    const b0 = Math.floor(f0 / L.block), b1 = Math.max(b0 + 1, Math.ceil(f1 / L.block));
    for (let b = b0; b < b1 && b < L.min.length; b++) {
      if (L.min[b] < mn) mn = L.min[b];
      if (L.max[b] > mx) mx = L.max[b];
    }
  }
  if (mn > mx) { mn = 0; mx = 0; }
  return [mn, mx];
}

const tToX = (t, W) => ((t - S.viewStart) / S.viewDur) * W;
const xToT = (x, W) => S.viewStart + (x / W) * S.viewDur;

function draw() {
  if (!S.buffer || $('editor').hidden) return;
  drawWave();
  drawOverview();
}

function drawWave() {
  const g = wave.getContext('2d');
  const W = wave.width, H = wave.height;
  g.clearRect(0, 0, W, H);
  const mid = H / 2, amp = H * 0.44;
  const xs = tToX(S.selStart, W), xe = tToX(S.selEnd, W);

  // fond de la sélection
  g.fillStyle = 'rgba(255,138,61,0.13)';
  g.fillRect(xs, 0, xe - xs, H);

  // graduations temporelles
  const step = niceStep(S.viewDur / (W / dpr / 80));
  g.fillStyle = '#5d6a88';
  g.font = `${11 * dpr}px system-ui, sans-serif`;
  g.textBaseline = 'top';
  for (let t = Math.ceil(S.viewStart / step) * step; t < S.viewStart + S.viewDur; t += step) {
    const x = tToX(t, W);
    g.fillRect(Math.round(x), 0, 1, 5 * dpr);
    g.fillText(fmtTime(t, step < 1 ? 1 : 0), x + 3 * dpr, 2 * dpr);
  }

  // forme d'onde
  const colW = 1; // un pixel physique par colonne
  for (let x = 0; x < W; x += colW) {
    const t0 = xToT(x, W), t1 = xToT(x + colW, W);
    if (t1 < 0 || t0 > S.duration) continue;
    const [mn, mx] = columnMinMax(Math.max(0, t0), Math.min(S.duration, t1));
    const inSel = x >= xs && x <= xe;
    g.fillStyle = inSel ? '#ffb27d' : '#4d6fa8';
    const y0 = mid - mx * amp, y1 = mid - mn * amp;
    g.fillRect(x, y0, colW, Math.max(1, y1 - y0));
  }
  g.fillStyle = 'rgba(255,255,255,0.08)';
  g.fillRect(0, Math.round(mid), W, 1);

  // fondus (aperçu)
  const fi = +$('fadeIn').value, fo = +$('fadeOut').value;
  g.strokeStyle = 'rgba(255,255,255,0.55)';
  g.lineWidth = 1.5 * dpr;
  if (fi > 0) { g.beginPath(); g.moveTo(xs, H - 2); g.lineTo(tToX(Math.min(S.selEnd, S.selStart + fi), W), 2 * dpr + 14 * dpr); g.stroke(); }
  if (fo > 0) { g.beginPath(); g.moveTo(tToX(Math.max(S.selStart, S.selEnd - fo), W), 2 * dpr + 14 * dpr); g.lineTo(xe, H - 2); g.stroke(); }

  // poignées
  drawHandle(g, xs, H, '#2dd4bf', 'D');
  drawHandle(g, xe, H, '#ff8a3d', 'F');

  // tête de lecture
  const xp = tToX(S.pos, W);
  if (xp >= 0 && xp <= W) {
    g.fillStyle = '#ffffff';
    g.fillRect(Math.round(xp) - dpr, 0, 2 * dpr, H);
  }
}

function drawHandle(g, x, H, color, label) {
  if (x < -30 * dpr || x > g.canvas.width + 30 * dpr) return;
  g.fillStyle = color;
  g.fillRect(Math.round(x) - dpr, 0, 2 * dpr, H);
  const r = 13 * dpr;
  g.beginPath();
  g.arc(x, H - r - 3 * dpr, r, 0, Math.PI * 2);
  g.fill();
  g.fillStyle = '#0b1019';
  g.font = `bold ${13 * dpr}px system-ui, sans-serif`;
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(label, x, H - r - 3 * dpr);
  g.textAlign = 'start';
}

function drawOverview() {
  const g = over.getContext('2d');
  const W = over.width, H = over.height;
  g.clearRect(0, 0, W, H);
  const mid = H / 2, amp = H * 0.45;
  const dur = S.duration;
  const L = S.peaks.lvl[1];
  const fs = S.buffer.sampleRate;
  const xs = (S.selStart / dur) * W, xe = (S.selEnd / dur) * W;
  for (let x = 0; x < W; x++) {
    const f0 = Math.floor((x / W) * dur * fs), f1 = Math.ceil(((x + 1) / W) * dur * fs);
    const b0 = Math.floor(f0 / L.block), b1 = Math.max(b0 + 1, Math.ceil(f1 / L.block));
    let mn = 1, mx = -1;
    for (let b = b0; b < b1 && b < L.min.length; b++) { if (L.min[b] < mn) mn = L.min[b]; if (L.max[b] > mx) mx = L.max[b]; }
    if (mn > mx) continue;
    g.fillStyle = x >= xs && x <= xe ? '#ff9a55' : '#3b5383';
    g.fillRect(x, mid - mx * amp, 1, Math.max(1, (mx - mn) * amp));
  }
  // fenêtre visible
  const vx = (S.viewStart / dur) * W, vw = Math.max(3 * dpr, (S.viewDur / dur) * W);
  g.strokeStyle = 'rgba(255,255,255,0.85)';
  g.lineWidth = 1.5 * dpr;
  g.strokeRect(vx + dpr, dpr, vw - 2 * dpr, H - 2 * dpr);
  g.fillStyle = '#fff';
  g.fillRect(Math.round((S.pos / dur) * W), 0, dpr, H);
}

function niceStep(raw) {
  const steps = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  for (const s of steps) if (s >= raw) return s;
  return 1200;
}

// ---------- Vue / zoom ----------
function clampView() {
  const minDur = Math.min(S.duration, 0.05);
  S.viewDur = clamp(S.viewDur, minDur, S.duration);
  S.viewStart = clamp(S.viewStart, 0, Math.max(0, S.duration - S.viewDur));
}
function zoomAt(factor, centerT) {
  const c = centerT ?? (S.viewStart + S.viewDur / 2);
  const rel = (c - S.viewStart) / S.viewDur;
  S.viewDur *= factor;
  clampView();
  S.viewStart = c - rel * S.viewDur;
  clampView();
  draw();
}
function viewSelection() {
  const d = S.selEnd - S.selStart;
  const pad = Math.max(0.5, d * 0.12);
  S.viewStart = S.selStart - pad;
  S.viewDur = d + 2 * pad;
  clampView();
  draw();
}
function ensureVisible(t) {
  if (t < S.viewStart || t > S.viewStart + S.viewDur) {
    S.viewStart = t - S.viewDur * 0.1;
    clampView();
  }
}

// ---------- Sélection ----------
function setSel(start, end, which) {
  start = clamp(start, 0, S.duration);
  end = clamp(end, 0, S.duration);
  if (end - start < MIN_SEL) {
    if (which === 'start') start = Math.max(0, end - MIN_SEL);
    else end = Math.min(S.duration, start + MIN_SEL);
  }
  S.selStart = start;
  S.selEnd = end;
  // si on écoute l'extrait, on relance pour prendre en compte les nouvelles bornes
  if (S.play && S.play.mode === 'sel') startPlayback('sel');
  updateSelUI();
}
function updateSelUI() {
  if (document.activeElement !== $('inStart')) $('inStart').value = fmtTime(S.selStart);
  if (document.activeElement !== $('inEnd')) $('inEnd').value = fmtTime(S.selEnd);
  $('selDur').textContent = fmtTime(S.selEnd - S.selStart);
  if (!S.nameTouched) $('outName').value = defaultName();
  draw();
}
function defaultName() {
  return sanitize(`${S.baseName} (extrait ${fileStamp(S.selStart)}-${fileStamp(S.selEnd)})`);
}

// ---------- Lecture ----------
function startPlayback(mode, from) {
  if (!S.buffer) return;
  const ctx = getCtx();
  stopPlayback(true);
  let start, end;
  if (mode === 'sel') { start = S.selStart; end = S.selEnd; }
  else {
    start = from ?? S.pos;
    if (start >= S.duration - 0.05) start = 0;
    end = S.duration;
  }
  const src = ctx.createBufferSource();
  src.buffer = S.buffer;
  const gain = ctx.createGain();
  src.connect(gain).connect(ctx.destination);
  const t0 = ctx.currentTime + 0.03;
  if (mode === 'sel') applyPreviewFx(gain.gain, t0, end - start);
  src.start(t0, start, end - start);
  const p = { src, gain, mode, from: start, to: end, t0 };
  src.onended = () => {
    if (S.play !== p) return;
    if (mode === 'sel' && S.loop) { startPlayback('sel'); return; }
    S.pos = mode === 'sel' ? S.selStart : Math.min(S.duration, end);
    stopPlayback();
  };
  S.play = p;
  updatePlayButtons();
  tick();
}
function applyPreviewFx(param, t0, len) {
  const lin = Math.pow(10, (+$('gain').value) / 20);
  let base = lin;
  if ($('normalize').checked) base = normGain();
  const fi = Math.min(+$('fadeIn').value, len / 2), fo = Math.min(+$('fadeOut').value, len / 2);
  param.setValueAtTime(fi > 0 ? 0.0001 : base, t0);
  if (fi > 0) param.linearRampToValueAtTime(base, t0 + fi);
  if (fo > 0) {
    param.setValueAtTime(base, t0 + len - fo);
    param.linearRampToValueAtTime(0.0001, t0 + len);
  }
}
let normCache = { key: '', g: 1 };
function normGain() {
  const key = `${S.selStart}|${S.selEnd}`;
  if (normCache.key === key) return normCache.g;
  const sr = S.buffer.sampleRate;
  const f0 = Math.floor(S.selStart * sr), f1 = Math.floor(S.selEnd * sr);
  let peak = 0;
  for (let c = 0; c < S.buffer.numberOfChannels; c++) {
    const d = S.buffer.getChannelData(c);
    for (let i = f0; i < f1; i++) { const a = Math.abs(d[i]); if (a > peak) peak = a; }
  }
  const g = peak > 0.0001 ? 0.891 / peak : 1; // -1 dBFS
  normCache = { key, g };
  return g;
}
function stopPlayback(silent) {
  if (S.play) {
    const p = S.play;
    S.play = null;
    try { p.src.onended = null; p.src.stop(); } catch { /* déjà arrêté */ }
    try { p.src.disconnect(); p.gain.disconnect(); } catch { /* rien */ }
  }
  if (!silent) { updatePlayButtons(); draw(); updatePos(); }
}
function currentPlayPos() {
  const p = S.play;
  if (!p) return S.pos;
  return clamp(p.from + (S.ctx.currentTime - p.t0), p.from, p.to);
}
function updatePlayButtons() {
  const full = S.play && S.play.mode === 'full';
  const sel = S.play && S.play.mode === 'sel';
  $('btnPlay').textContent = full ? '❚❚' : '▶';
  $('btnPreview').textContent = sel ? '■ Arrêter' : '▶ Écouter l’extrait';
}
function updatePos() { $('posTime').textContent = fmtTime(S.pos); }
let rafId = 0;
function tick() {
  cancelAnimationFrame(rafId);
  if (!S.play) return;
  S.pos = currentPlayPos();
  if (!drag && S.play.mode === 'full') ensureVisible(S.pos);
  updatePos();
  draw();
  rafId = requestAnimationFrame(tick);
}
function seek(t) {
  S.pos = clamp(t, 0, S.duration);
  if (S.play && S.play.mode === 'full') startPlayback('full', S.pos);
  else if (S.play) stopPlayback();
  updatePos();
  draw();
}

// ---------- Gestes sur la forme d'onde ----------
const pointers = new Map();
let drag = null;
function canvasX(e) {
  const r = wave.getBoundingClientRect();
  return (e.clientX - r.left) * dpr;
}
wave.addEventListener('pointerdown', (e) => {
  if (!S.buffer) return;
  wave.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, canvasX(e));
  const W = wave.width;
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()];
    drag = { type: 'pinch', dist: Math.abs(a - b) || 1, center: xToT((a + b) / 2, W), cx: (a + b) / 2, dur: S.viewDur };
    return;
  }
  const x = canvasX(e);
  const tol = 30 * dpr;
  const ds = Math.abs(x - tToX(S.selStart, W)), de = Math.abs(x - tToX(S.selEnd, W));
  if (Math.min(ds, de) < tol) {
    drag = { type: de <= ds ? 'end' : 'start', x0: x };
  } else {
    drag = { type: 'pan?', x0: x, vs: S.viewStart };
  }
});
wave.addEventListener('pointermove', (e) => {
  if (!drag || !pointers.has(e.pointerId)) return;
  pointers.set(e.pointerId, canvasX(e));
  const W = wave.width;
  const x = canvasX(e);
  if (drag.type === 'pinch' && pointers.size >= 2) {
    const [a, b] = [...pointers.values()];
    const dist = Math.abs(a - b) || 1;
    S.viewDur = drag.dur * (drag.dist / dist);
    clampView();
    S.viewStart = drag.center - (drag.cx / W) * S.viewDur;
    clampView();
    draw();
  } else if (drag.type === 'start') {
    setSel(Math.min(xToT(x, W), S.selEnd - MIN_SEL), S.selEnd, 'start');
  } else if (drag.type === 'end') {
    setSel(S.selStart, Math.max(xToT(x, W), S.selStart + MIN_SEL), 'end');
  } else if (drag.type === 'pan?' && Math.abs(x - drag.x0) > 10 * dpr) {
    drag.type = 'pan';
  }
  if (drag.type === 'pan') {
    S.viewStart = drag.vs - ((x - drag.x0) / W) * S.viewDur;
    clampView();
    draw();
  }
});
function endPointer(e) {
  if (!pointers.has(e.pointerId)) return;
  const x = pointers.get(e.pointerId);
  pointers.delete(e.pointerId);
  if (!drag) return;
  if (drag.type === 'pan?') seek(xToT(x, wave.width));
  if (drag.type === 'pinch' && pointers.size === 1) {
    const [x1] = [...pointers.values()];
    drag = { type: 'pan', x0: x1, vs: S.viewStart };
    return;
  }
  if (pointers.size === 0) drag = null;
}
wave.addEventListener('pointerup', endPointer);
wave.addEventListener('pointercancel', endPointer);
wave.addEventListener('wheel', (e) => {
  e.preventDefault();
  const t = xToT(canvasX(e), wave.width);
  zoomAt(e.deltaY > 0 ? 1.25 : 0.8, t);
}, { passive: false });

// barre d'aperçu : toucher / glisser pour déplacer la vue
function overviewMove(e) {
  const r = over.getBoundingClientRect();
  const t = ((e.clientX - r.left) / r.width) * S.duration;
  S.viewStart = t - S.viewDur / 2;
  clampView();
  draw();
}
over.addEventListener('pointerdown', (e) => { if (!S.buffer) return; over.setPointerCapture(e.pointerId); over._drag = true; overviewMove(e); });
over.addEventListener('pointermove', (e) => { if (over._drag) overviewMove(e); });
over.addEventListener('pointerup', () => { over._drag = false; });
over.addEventListener('pointercancel', () => { over._drag = false; });

// ---------- Export ----------
let worker = null;
function encodeMp3(channels, sampleRate, kbps, onProgress) {
  if (!worker) worker = new Worker('encoder-worker.js');
  return new Promise((resolve, reject) => {
    worker.onmessage = (e) => {
      if (e.data.error) reject(new Error(e.data.error));
      else if (e.data.done) resolve(e.data.blob);
      else if (e.data.progress != null) onProgress(e.data.progress);
    };
    worker.onerror = (e) => reject(new Error(e.message || 'encodeur'));
    worker.postMessage({ channels, sampleRate, kbps }, channels.map((c) => c.buffer));
  });
}

function blobToBase64(blob) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(',')[1]);
    r.onerror = rej;
    r.readAsDataURL(blob);
  });
}

async function ensureStoragePermission() {
  try {
    const st = await Filesystem.checkPermissions();
    if (st.publicStorage !== 'granted') {
      const r = await Filesystem.requestPermissions();
      return r.publicStorage === 'granted';
    }
  } catch { /* Android 11+ : pas de permission nécessaire */ }
  return true;
}

async function uniquePath(name, ext, directory) {
  let candidate = `${FOLDER}/${name}.${ext}`;
  for (let i = 2; i < 100; i++) {
    try { await Filesystem.stat({ path: candidate, directory }); }
    catch { return candidate; }
    candidate = `${FOLDER}/${name} (${i}).${ext}`;
  }
  return `${FOLDER}/${name} ${Date.now()}.${ext}`;
}

async function writeNative(blob, name, ext) {
  const data = await blobToBase64(blob);
  await ensureStoragePermission();
  // 1er choix : Documents/Extrays (visible dans le gestionnaire de fichiers)
  try {
    const path = await uniquePath(name, ext, Directory.Documents);
    await Filesystem.writeFile({ path, data, directory: Directory.Documents, recursive: true });
    const { uri } = await Filesystem.getUri({ path, directory: Directory.Documents });
    return { path, directory: 'DOCUMENTS', uri, where: 'Documents/Extrays' };
  } catch (e) {
    console.warn('Documents indisponible, repli', e);
  }
  // repli : dossier de l'appli sur le stockage externe
  const path = await uniquePath(name, ext, Directory.External);
  await Filesystem.writeFile({ path, data, directory: Directory.External, recursive: true });
  const { uri } = await Filesystem.getUri({ path, directory: Directory.External });
  return { path, directory: 'EXTERNAL', uri, where: 'Android/data/com.echomatras.extrays/files/Extrays' };
}

function downloadWeb(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

async function saveExtract() {
  if (!S.buffer || S.busy) return;
  stopPlayback();
  const name = sanitize($('outName').value || defaultName());
  const [kind, kbpsStr] = S.fmt.split('-');
  const ext = kind === 'wav' ? 'wav' : 'mp3';
  $('btnSave').disabled = true;
  $('progress').hidden = false;
  setProgress(0.02);
  try {
    const opts = {
      start: S.selStart, end: S.selEnd,
      fadeIn: +$('fadeIn').value, fadeOut: +$('fadeOut').value,
      gainDb: +$('gain').value, normalize: $('normalize').checked,
    };
    let { channels, sampleRate } = await renderSelection(S.buffer, opts, ext === 'mp3');
    setProgress(0.08);
    let blob;
    if (ext === 'wav') {
      blob = encodeWav(channels, sampleRate);
    } else {
      blob = await encodeMp3(channels, sampleRate, parseInt(kbpsStr, 10), (p) => setProgress(0.08 + p * 0.85));
    }
    setProgress(0.95);
    const filename = `${name}.${ext}`;
    const entry = {
      id: Date.now().toString(36),
      name: filename,
      date: Date.now(),
      duration: S.selEnd - S.selStart,
      size: blob.size,
      fmt: S.fmt,
      source: S.fileName,
    };
    if (NATIVE) {
      const r = await writeNative(blob, name, ext);
      entry.path = r.path; entry.directory = r.directory; entry.uri = r.uri;
      entry.name = r.path.split('/').pop();
      addHistory(entry);
      setProgress(1);
      toast(`Enregistré : ${r.directory === 'DOCUMENTS' ? 'Documents/Extrays' : r.where}`, {
        action: { label: 'Partager', fn: () => shareEntry(entry) },
      });
    } else {
      downloadWeb(blob, filename);
      entry.web = true;
      addHistory(entry);
      setProgress(1);
      toast(`Téléchargé : ${filename}`);
    }
  } catch (e) {
    console.error(e);
    toast(`Échec de l'enregistrement : ${e.message || e}`, { error: true, ms: 6000 });
  } finally {
    $('btnSave').disabled = false;
    setTimeout(() => { $('progress').hidden = true; setProgress(0); }, 700);
  }
}
function setProgress(p) { $('progressBar').style.width = `${Math.round(p * 100)}%`; }

// ---------- Historique ----------
function getHistory() { return loadJSON(HIST_KEY, []); }
function addHistory(entry) {
  const h = getHistory();
  h.unshift(entry);
  saveJSON(HIST_KEY, h.slice(0, 200));
}
function removeHistory(id) { saveJSON(HIST_KEY, getHistory().filter((e) => e.id !== id)); }

let histPlaying = null;
function renderHistory() {
  const list = $('histList');
  const h = getHistory();
  list.innerHTML = '';
  $('histEmpty').hidden = h.length > 0;
  $('histCount').textContent = h.length ? `${h.length}` : '';
  for (const e of h) {
    const li = document.createElement('li');
    const d = new Date(e.date);
    const fmtLabel = e.fmt === 'wav' ? 'WAV' : `MP3 ${e.fmt.split('-')[1]}`;
    li.innerHTML = `
      <div class="info">
        <div class="name"></div>
        <div class="muted small">${fmtTime(e.duration)} · ${fmtLabel} · ${fmtSize(e.size)} · ${d.toLocaleDateString('fr-FR')} ${d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</div>
      </div>
      <div class="acts"></div>`;
    li.querySelector('.name').textContent = e.name;
    const acts = li.querySelector('.acts');
    if (!e.web) {
      const play = mkBtn(histPlaying === e.id ? '■' : '▶', 'Écouter', () => toggleHistPlay(e));
      if (histPlaying === e.id) play.classList.add('playing');
      acts.append(play, mkBtn('⇪', 'Partager', () => shareEntry(e)));
    }
    acts.append(mkBtn('✕', 'Supprimer', () => deleteEntry(e)));
    list.appendChild(li);
  }
}
function mkBtn(txt, label, fn) {
  const b = document.createElement('button');
  b.className = 'btn';
  b.textContent = txt;
  b.setAttribute('aria-label', label);
  b.title = label;
  b.onclick = fn;
  return b;
}
async function readEntryBlob(e) {
  const r = await Filesystem.readFile({ path: e.path, directory: Directory[e.directory] });
  const bin = atob(r.data);
  const u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new Blob([u8], { type: e.name.endsWith('.wav') ? 'audio/wav' : 'audio/mpeg' });
}
async function toggleHistPlay(e) {
  const audio = $('histAudio');
  if (histPlaying === e.id) {
    audio.pause(); histPlaying = null; renderHistory(); return;
  }
  try {
    const blob = await readEntryBlob(e);
    if (audio.src) URL.revokeObjectURL(audio.src);
    audio.src = URL.createObjectURL(blob);
    audio.onended = () => { histPlaying = null; renderHistory(); };
    await audio.play();
    histPlaying = e.id;
    renderHistory();
  } catch (err) {
    console.error(err);
    toast('Fichier introuvable (déplacé ou supprimé ?)', { error: true });
  }
}
async function shareEntry(e) {
  try {
    if (NATIVE) {
      await Share.share({ title: e.name, files: [e.uri], dialogTitle: 'Partager l’extrait' });
    }
  } catch (err) {
    if (!String(err?.message || err).toLowerCase().includes('cancel')) {
      toast('Partage impossible', { error: true });
    }
  }
}
async function deleteEntry(e) {
  if (!confirm(`Supprimer « ${e.name} » ?`)) return;
  if (!e.web) {
    try { await Filesystem.deleteFile({ path: e.path, directory: Directory[e.directory] }); }
    catch { /* déjà supprimé */ }
  }
  if (histPlaying === e.id) { $('histAudio').pause(); histPlaying = null; }
  removeHistory(e.id);
  renderHistory();
}

// ---------- Préférences ----------
function savePrefs() {
  saveJSON(PREF_KEY, {
    fmt: S.fmt, loop: S.loop,
    fadeIn: $('fadeIn').value, fadeOut: $('fadeOut').value,
    gain: $('gain').value, normalize: $('normalize').checked,
  });
}
function loadPrefs() {
  const p = loadJSON(PREF_KEY, {});
  if (p.fmt) S.fmt = p.fmt;
  S.loop = !!p.loop;
  if (p.fadeIn != null) $('fadeIn').value = p.fadeIn;
  if (p.fadeOut != null) $('fadeOut').value = p.fadeOut;
  if (p.gain != null) $('gain').value = p.gain;
  $('normalize').checked = !!p.normalize;
}
function updateOptsUI() {
  const fi = +$('fadeIn').value, fo = +$('fadeOut').value, gn = +$('gain').value;
  $('fadeInVal').textContent = `${fi} s`;
  $('fadeOutVal').textContent = `${fo} s`;
  $('gainVal').textContent = `${gn > 0 ? '+' : ''}${gn} dB`;
  $('gain').disabled = $('normalize').checked;
  const parts = [];
  if (fi) parts.push(`fondu ${fi}s`);
  if (fo) parts.push(`fin ${fo}s`);
  if ($('normalize').checked) parts.push('normalisé');
  else if (gn) parts.push(`${gn > 0 ? '+' : ''}${gn} dB`);
  $('optSummary').textContent = parts.length ? `(${parts.join(', ')})` : '';
  document.querySelectorAll('.fmt').forEach((b) => b.classList.toggle('on', b.dataset.fmt === S.fmt));
  $('btnLoop').setAttribute('aria-pressed', String(S.loop));
  draw();
}

// ---------- Liaisons ----------
function bind() {
  const pick = () => { getCtx(); $('fileInput').click(); };
  $('btnOpen').onclick = pick;
  $('btnOpenTop').onclick = pick;
  $('btnResume').onclick = () => showScreen('editor');
  $('btnHome').onclick = () => showScreen('home');
  $('fileInput').onchange = (e) => openFile(e.target.files[0]);

  $('btnPlay').onclick = () => {
    if (S.play && S.play.mode === 'full') { S.pos = currentPlayPos(); stopPlayback(); }
    else startPlayback('full');
  };
  $('btnPreview').onclick = () => {
    if (S.play && S.play.mode === 'sel') { stopPlayback(); }
    else startPlayback('sel');
  };
  $('btnLoop').onclick = () => { S.loop = !S.loop; savePrefs(); updateOptsUI(); };
  $('back5').onclick = () => seek((S.play ? currentPlayPos() : S.pos) - 5);
  $('fwd5').onclick = () => seek((S.play ? currentPlayPos() : S.pos) + 5);

  $('setStart').onclick = () => {
    const t = S.play ? currentPlayPos() : S.pos;
    if (t >= S.selEnd - MIN_SEL) setSel(t, Math.min(S.duration, t + 30), 'start');
    else setSel(t, S.selEnd, 'start');
  };
  $('setEnd').onclick = () => {
    const t = S.play ? currentPlayPos() : S.pos;
    if (t <= S.selStart + MIN_SEL) toast('La fin doit être après le début', { error: true });
    else setSel(S.selStart, t, 'end');
  };
  document.querySelectorAll('[data-nudge]').forEach((b) => {
    b.onclick = () => {
      const [which, d] = b.dataset.nudge.split(':');
      if (which === 'start') setSel(Math.min(S.selStart + +d, S.selEnd - MIN_SEL), S.selEnd, 'start');
      else setSel(S.selStart, Math.max(S.selEnd + +d, S.selStart + MIN_SEL), 'end');
      ensureVisible(which === 'start' ? S.selStart : S.selEnd);
      draw();
    };
  });
  const timeInput = (el, which) => {
    el.onchange = () => {
      const t = parseTime(el.value);
      if (isNaN(t)) { toast('Format attendu : 1:23.4 ou 83.4', { error: true }); updateSelUI(); return; }
      if (which === 'start') setSel(Math.min(t, S.selEnd - MIN_SEL), S.selEnd, 'start');
      else setSel(S.selStart, Math.max(t, S.selStart + MIN_SEL), 'end');
      ensureVisible(t);
      updateSelUI();
    };
    el.onfocus = () => el.select();
    el.onkeydown = (e) => { if (e.key === 'Enter') el.blur(); };
  };
  timeInput($('inStart'), 'start');
  timeInput($('inEnd'), 'end');

  $('zoomIn').onclick = () => zoomAt(0.5, S.play ? S.pos : undefined);
  $('zoomOut').onclick = () => zoomAt(2, S.play ? S.pos : undefined);
  $('zoomSel').onclick = viewSelection;
  $('zoomAll').onclick = () => { S.viewStart = 0; S.viewDur = S.duration; draw(); };

  for (const id of ['fadeIn', 'fadeOut', 'gain', 'normalize']) {
    $(id).addEventListener('input', () => { updateOptsUI(); savePrefs(); });
  }
  document.querySelectorAll('.fmt').forEach((b) => {
    b.onclick = () => { S.fmt = b.dataset.fmt; savePrefs(); updateOptsUI(); };
  });
  $('outName').addEventListener('input', () => { S.nameTouched = true; });
  $('btnSave').onclick = saveExtract;

  window.addEventListener('resize', () => { resizeCanvases(); draw(); });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && S.play) { S.pos = currentPlayPos(); stopPlayback(); }
  });

  // glisser-déposer (navigateur / Windows)
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => {
    e.preventDefault();
    const f = e.dataTransfer?.files?.[0];
    if (f) { getCtx(); openFile(f); }
  });

  if (NATIVE) {
    App.addListener('backButton', () => {
      if (S.busy) return;
      if (!$('editor').hidden) showScreen('home');
      else App.exitApp();
    });
  }
}

loadPrefs();
bind();
updateOptsUI();
renderHistory();

// accès pour les tests automatisés
window.__extrays = { S, openFile, setSel, saveExtract, startPlayback, stopPlayback };
