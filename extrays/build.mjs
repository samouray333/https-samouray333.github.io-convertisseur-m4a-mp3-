// Construit le dossier www/ (bundle esbuild + fichiers statiques)
import { build } from 'esbuild';
import { mkdirSync, copyFileSync, rmSync } from 'node:fs';
rmSync('www', { recursive: true, force: true });
mkdirSync('www', { recursive: true });
for (const f of ['index.html', 'style.css', 'encoder-worker.js']) copyFileSync(`src/${f}`, `www/${f}`);
copyFileSync('assets/icon.svg', 'www/icon.svg');
copyFileSync('node_modules/lamejs/lame.min.js', 'www/lame.min.js');
await build({
  entryPoints: ['src/app.js'], bundle: true, format: 'iife', minify: true,
  target: ['chrome80'], outfile: 'www/app.js', sourcemap: false,
});
console.log('www/ prêt');
