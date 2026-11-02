// Génère les icônes et écrans de démarrage à partir de src/assets/logo.svg (Chromium headless).
// Usage : node tools/icons.cjs
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const logo = fs.readFileSync(path.join(root, 'src/assets/logo.svg'), 'utf8');
const fg = fs.readFileSync(path.join(root, 'build/logo-foreground.svg'), 'utf8');

async function render(page, html, w, h, out) {
  await page.setViewportSize({ width: w, height: h });
  await page.setContent(`<html><body style="margin:0;background:transparent">${html}</body></html>`);
  fs.mkdirSync(path.dirname(out), { recursive: true });
  await page.screenshot({ path: out, omitBackground: true, clip: { x: 0, y: 0, width: w, height: h } });
}

function ico(pngs, out) {
  const n = pngs.length;
  const head = Buffer.alloc(6 + 16 * n);
  head.writeUInt16LE(0, 0);
  head.writeUInt16LE(1, 2);
  head.writeUInt16LE(n, 4);
  let off = head.length;
  pngs.forEach(({ size, buf }, i) => {
    const e = 6 + 16 * i;
    head.writeUInt8(size >= 256 ? 0 : size, e);
    head.writeUInt8(size >= 256 ? 0 : size, e + 1);
    head.writeUInt16LE(1, e + 4);
    head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(buf.length, e + 8);
    head.writeUInt32LE(off, e + 12);
    off += buf.length;
  });
  fs.writeFileSync(out, Buffer.concat([head, ...pngs.map((p) => p.buf)]));
}

(async () => {
  const b = await chromium.launch();
  const page = await b.newPage();
  const svg = (s, size) => s.replace('<svg ', `<svg width="${size}" height="${size}" `);
  // Windows / Electron
  await render(page, svg(logo, 512), 512, 512, path.join(root, 'build/icon.png'));
  const sizes = [16, 24, 32, 48, 64, 128, 256];
  const pngs = [];
  for (const s of sizes) {
    const f = path.join(root, `build/tmp_${s}.png`);
    await render(page, svg(logo, s), s, s, f);
    pngs.push({ size: s, buf: fs.readFileSync(f) });
    fs.unlinkSync(f);
  }
  ico(pngs, path.join(root, 'build/icon.ico'));
  // Android : icônes classiques, rondes et adaptatives
  const res = path.join(root, 'android/app/src/main/res');
  const dens = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
  if (fs.existsSync(res)) {
    for (const [d, k] of Object.entries(dens)) {
      const s = Math.round(48 * k);
      await render(page, svg(logo, s), s, s, `${res}/mipmap-${d}/ic_launcher.png`);
      await render(page, `<div style="width:${s}px;height:${s}px;border-radius:50%;overflow:hidden">${svg(logo.replace('rx="112"', 'rx="256"'), s)}</div>`, s, s, `${res}/mipmap-${d}/ic_launcher_round.png`);
      const f = Math.round(108 * k);
      await render(page, svg(fg, f), f, f, `${res}/mipmap-${d}/ic_launcher_foreground.png`);
    }
    // écran de démarrage
    const splash = (w, h) => `<div style="width:${w}px;height:${h}px;background:#0f4c5c;display:flex;flex-direction:column;align-items:center;justify-content:center;font-family:sans-serif;color:#fff">${svg(logo, Math.round(Math.min(w, h) * 0.28))}<div style="font-size:${Math.round(Math.min(w, h) * 0.07)}px;font-weight:700;margin-top:${Math.round(Math.min(w, h) * 0.04)}px;letter-spacing:2px">Bimys</div><div style="font-size:${Math.round(Math.min(w, h) * 0.028)}px;opacity:.75;margin-top:8px">QMTech</div></div>`;
    await render(page, splash(1280, 1280), 1280, 1280, `${res}/drawable/splash.png`);
    for (const [d, k] of Object.entries(dens)) {
      await render(page, splash(Math.round(320 * k), Math.round(480 * k)), Math.round(320 * k), Math.round(480 * k), `${res}/drawable-port-${d}/splash.png`);
      await render(page, splash(Math.round(480 * k), Math.round(320 * k)), Math.round(480 * k), Math.round(320 * k), `${res}/drawable-land-${d}/splash.png`);
    }
  }
  await b.close();
  console.log('Icônes générées.');
})();
