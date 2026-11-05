// Moteur audio d'Extrays : découpe, fondus, volume, WAV

const MP3_RATES = [8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000];

/**
 * Extrait la sélection d'un AudioBuffer en appliquant volume / normalisation et fondus.
 * Retourne { channels: Float32Array[], sampleRate }. Au plus 2 canaux.
 */
export async function renderSelection(buffer, opts, forMp3) {
  const sr = buffer.sampleRate;
  const f0 = Math.max(0, Math.floor(opts.start * sr));
  const f1 = Math.min(buffer.length, Math.floor(opts.end * sr));
  const len = Math.max(1, f1 - f0);
  const nCh = Math.min(2, buffer.numberOfChannels);
  let channels = [];
  for (let c = 0; c < nCh; c++) channels.push(buffer.getChannelData(c).slice(f0, f0 + len));

  // volume
  let g = Math.pow(10, (opts.gainDb || 0) / 20);
  if (opts.normalize) {
    let peak = 0;
    for (const d of channels) for (let i = 0; i < d.length; i++) { const a = Math.abs(d[i]); if (a > peak) peak = a; }
    g = peak > 0.0001 ? 0.891 / peak : 1; // -1 dBFS
  }

  // fondus (courbe en S douce, limités à la moitié de l'extrait)
  const fi = Math.min(Math.round((opts.fadeIn || 0) * sr), Math.floor(len / 2));
  const fo = Math.min(Math.round((opts.fadeOut || 0) * sr), Math.floor(len / 2));
  for (const d of channels) {
    for (let i = 0; i < len; i++) {
      let k = g;
      if (i < fi) k *= curve(i / fi);
      if (i >= len - fo) k *= curve((len - 1 - i) / fo);
      let v = d[i] * k;
      if (v > 1) v = 1; else if (v < -1) v = -1;
      d[i] = v;
    }
  }

  let outRate = sr;
  if (forMp3 && !MP3_RATES.includes(sr)) {
    outRate = sr > 44100 ? 48000 : 44100;
    channels = await resample(channels, sr, outRate);
  }
  return { channels, sampleRate: outRate };
}

function curve(x) {
  // demi-sinus : départ et arrivée en douceur
  return 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, x)));
}

async function resample(channels, from, to) {
  const len = channels[0].length;
  const outLen = Math.max(1, Math.round((len * to) / from));
  const OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  const src = new OAC(channels.length, len, from).createBuffer(channels.length, len, from);
  channels.forEach((d, c) => src.copyToChannel(d, c));
  const off = new OAC(channels.length, outLen, to);
  const node = off.createBufferSource();
  node.buffer = src;
  node.connect(off.destination);
  node.start();
  const out = await off.startRendering();
  return channels.map((_, c) => out.getChannelData(c).slice());
}

/** Encode des canaux float en WAV PCM 16 bits. */
export function encodeWav(channels, sampleRate) {
  const nCh = channels.length;
  const len = channels[0].length;
  const bytes = 44 + len * nCh * 2;
  const buf = new ArrayBuffer(bytes);
  const v = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); v.setUint32(4, bytes - 8, true); w(8, 'WAVE');
  w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, nCh, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * nCh * 2, true);
  v.setUint16(32, nCh * 2, true); v.setUint16(34, 16, true);
  w(36, 'data'); v.setUint32(40, len * nCh * 2, true);
  let o = 44;
  for (let i = 0; i < len; i++) {
    for (let c = 0; c < nCh; c++) {
      const s = Math.max(-1, Math.min(1, channels[c][i]));
      v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      o += 2;
    }
  }
  return new Blob([buf], { type: 'audio/wav' });
}
