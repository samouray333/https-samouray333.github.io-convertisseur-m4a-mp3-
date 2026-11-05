/* Encodeur MP3 d'Extrays (lamejs, LGPL), exécuté hors du fil principal */
importScripts('lame.min.js');

function toInt16(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = f32[i] > 1 ? 1 : f32[i] < -1 ? -1 : f32[i];
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

onmessage = (e) => {
  try {
    const { channels, sampleRate, kbps } = e.data;
    const nCh = channels.length;
    const enc = new lamejs.Mp3Encoder(nCh, sampleRate, kbps);
    const L = toInt16(channels[0]);
    const R = nCh > 1 ? toInt16(channels[1]) : null;
    const len = L.length;
    const block = 1152 * 32;
    const parts = [];
    let n = 0;
    for (let i = 0; i < len; i += block) {
      const out = R
        ? enc.encodeBuffer(L.subarray(i, i + block), R.subarray(i, i + block))
        : enc.encodeBuffer(L.subarray(i, i + block));
      if (out.length) parts.push(new Uint8Array(out));
      if (++n % 8 === 0) postMessage({ progress: i / len });
    }
    const end = enc.flush();
    if (end.length) parts.push(new Uint8Array(end));
    postMessage({ done: true, blob: new Blob(parts, { type: 'audio/mpeg' }) });
  } catch (err) {
    postMessage({ error: String(err && err.message || err) });
  }
};
