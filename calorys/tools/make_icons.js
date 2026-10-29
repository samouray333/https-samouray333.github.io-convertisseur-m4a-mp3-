// Génère les PNG d'icônes (web, Android, Windows) à partir de app/img/icon.svg.
// Usage : node tools/make_icons.js   (nécessite Playwright + Chromium)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const svg = fs.readFileSync(path.join(ROOT, 'app/img/icon.svg'), 'utf8');
const inner = svg.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');
const defs = inner.match(/<defs>[\s\S]*?<\/defs>/)[0];
const art = inner.replace(defs, '').replace(/<rect[^>]*\/>/, '');
const variants = {
  full: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">${inner}</svg>`,
  // Calque de fond adaptatif : dégradé plein cadre.
  bg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">${defs}<rect width="512" height="512" fill="url(#g)"/></svg>`,
  // Calque avant : motif réduit dans la zone de sécurité (66/108).
  fg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-96 -96 704 704">${art}</svg>`
};
const dens = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
const jobs = [
  ['full', 192, 'app/img/icon-192.png'], ['full', 512, 'app/img/icon-512.png'],
  ['full', 256, 'windows/icon-256.png']
];
for (const [d, f] of Object.entries(dens)) {
  jobs.push(['full', 48 * f, `android/res/mipmap-${d}/ic_launcher.png`]);
  jobs.push(['bg', 108 * f, `android/res/mipmap-${d}/ic_launcher_bg.png`]);
  jobs.push(['fg', 108 * f, `android/res/mipmap-${d}/ic_launcher_fg.png`]);
}
for (const s of [16, 24, 32, 48, 64, 128, 256]) jobs.push(['full', s, `windows/ico/icon-${s}.png`]);
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage();
  for (const [v, size, out] of jobs) {
    const file = path.join(ROOT, out);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    await p.setViewportSize({ width: size, height: size });
    await p.setContent(`<html><body style="margin:0;background:transparent">${variants[v].replace('<svg ', `<svg width="${size}" height="${size}" `)}</body></html>`);
    await p.screenshot({ path: file, omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } });
  }
  await b.close();
  console.log(jobs.length + ' icônes générées');
})();
