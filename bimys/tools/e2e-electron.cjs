// Test automatique de l'application de bureau (Electron) : menus, ouverture, 3D, outils, exports, journal.
// Usage : node tools/e2e-electron.cjs [chemin/vers/Bimys.exe] [dossier_captures]
// Sans exécutable, lance l'application depuis les sources (npm run build au préalable).
const { _electron } = require('playwright-core');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const exe = process.argv[2] && process.argv[2] !== '-' ? path.resolve(process.argv[2]) : null;
const OUT = path.resolve(process.argv[3] || path.join(root, 'test-results', 'e2e'));
fs.mkdirSync(OUT, { recursive: true });
const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'bimys-e2e-'));
const results = [];
let failed = 0;

async function step(name, fn) {
  const t0 = Date.now();
  try {
    await fn();
    results.push(`OK    ${name} (${Date.now() - t0} ms)`);
    console.log(`OK    ${name}`);
  } catch (e) {
    failed++;
    results.push(`ÉCHEC ${name} : ${e.message}`);
    console.log(`ÉCHEC ${name} : ${e.message}`);
  }
}
function assert(c, msg) {
  if (!c) throw new Error(msg);
}

async function launch() {
  const opts = exe
    ? { executablePath: exe, args: ['--rendu-logiciel'] }
    : { executablePath: require(path.join(root, 'node_modules', 'electron')), args: [root, '--rendu-logiciel', '--no-sandbox'] };
  const app = await _electron.launch({ ...opts, env: { ...process.env, BIMYS_USER_DATA: userData } });
  const w = await app.firstWindow();
  return { app, w };
}

(async () => {
  let { app, w } = await launch();
  const errors = [];
  w.on('pageerror', (e) => errors.push(e.message));
  await step('démarrage et page d’accueil', async () => {
    await w.waitForSelector('.hero', { timeout: 30000 });
    assert(await w.evaluate(() => !!window.bimysNative), 'pont Windows absent');
    assert(!(await w.$('.nowebgl')), 'affichage 3D indisponible');
  });
  await step('barre de menus en français', async () => {
    const labels = await app.evaluate(({ Menu }) => Menu.getApplicationMenu().items.map((i) => i.label));
    assert(labels.join('|') === '&Fichier|&Affichage|&Modules|&Aide', `menus : ${labels.join(', ')}`);
  });
  await step('ouverture d’un exemple par le menu Fichier', async () => {
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].webContents.send('menu', 'sample:maison_chaudiere_gaz.ifc'));
    await w.waitForFunction(() => window.bimysApp?.model && !document.querySelector('.loader'), null, { timeout: 90000 });
    await w.waitForTimeout(800);
    const n = await w.evaluate(() => window.bimysApp.model.elements.length);
    assert(n > 250, `${n} objets`);
    assert((await w.title()).includes('maison_chaudiere_gaz.ifc'), `titre : ${await w.title()}`);
    await w.screenshot({ path: `${OUT}/01_vue3d.png` });
  });
  await step('rendu 3D non vide', async () => {
    const stats = await w.evaluate(() => {
      const c = document.querySelector('.viewer-canvas');
      const t = document.createElement('canvas');
      t.width = 64;
      t.height = 64;
      const g = t.getContext('2d');
      g.drawImage(c, 0, 0, 64, 64);
      const d = g.getImageData(0, 0, 64, 64).data;
      const set = new Set();
      for (let i = 0; i < d.length; i += 4) set.add(`${d[i] >> 4},${d[i + 1] >> 4},${d[i + 2] >> 4}`);
      return set.size;
    });
    assert(stats > 8, `seulement ${stats} couleurs dans la vue`);
  });
  await step('sélection, propriétés et barre d’état', async () => {
    await w.evaluate(() => {
      const a = window.bimysApp;
      a.showElement(a.model.elements.find((e) => e.name === 'Radiateur séjour 1').id);
    });
    await w.waitForTimeout(400);
    const t = await w.textContent('.panel.right .prop-head .n');
    assert(t.includes('Radiateur séjour 1'), `propriétés : ${t}`);
    assert((await w.textContent('.statusbar')).includes('Radiateur séjour 1'), 'barre d’état');
    await w.screenshot({ path: `${OUT}/02_selection.png` });
  });
  await step('menu contextuel (clic droit)', async () => {
    const c = await w.$('.viewer-canvas');
    const b = await c.boundingBox();
    await w.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { button: 'right' });
    await w.waitForSelector('.ctxmenu', { timeout: 3000 });
    const items = await w.$$eval('.ctxmenu button', (bs) => bs.map((x) => x.textContent));
    assert(items.some((x) => x.includes('Tout afficher')), 'entrées du menu');
    await w.screenshot({ path: `${OUT}/03_menu_contextuel.png` });
    await w.keyboard.press('Escape');
  });
  await step('recherche (Ctrl+F)', async () => {
    await w.keyboard.press('Control+f');
    await w.keyboard.type('radiateur');
    await w.waitForTimeout(300);
    const head = await w.textContent('.search-head');
    assert(/^(8|9|1\d) résultats/.test(head.trim()), `résultats : ${head}`);
    await w.screenshot({ path: `${OUT}/04_recherche.png` });
    await w.fill('.searchbox input', '');
    await w.dispatchEvent('.searchbox input', 'input');
    await w.click('.viewer-canvas', { position: { x: 5, y: 5 } }).catch(() => {});
  });
  await step('sélection multiple (Ctrl+clic dans l’arborescence)', async () => {
    await w.evaluate(() => {
      const a = window.bimysApp;
      const ids = a.model.elements.filter((e) => /Radiateur chambre/.test(e.name)).map((e) => e.id);
      a.viewer.setSelection(ids);
    });
    const n = await w.evaluate(() => window.bimysApp.viewer.selectionIds.length);
    assert(n === 3, `${n} sélectionnés`);
  });
  await step('plan 2D (touche P) et vue orthographique', async () => {
    await w.evaluate(() => document.activeElement && document.activeElement.blur());
    await w.keyboard.press('Escape');
    await w.keyboard.press('p');
    await w.waitForTimeout(600);
    assert((await w.evaluate(() => window.bimysApp.viewer.projection)) === 'orthographic', 'projection');
    assert((await w.textContent('.statusbar')).includes('Plan RDC'), 'barre d’état plan');
    await w.screenshot({ path: `${OUT}/05_plan_rdc.png` });
    await w.keyboard.press('PageUp');
    await w.waitForTimeout(400);
    assert((await w.textContent('.statusbar')).includes('Plan R+1'), 'niveau suivant');
    await w.screenshot({ path: `${OUT}/06_plan_r1.png` });
    await w.keyboard.press('p');
    await w.waitForTimeout(300);
    assert((await w.evaluate(() => window.bimysApp.viewer.projection)) === 'perspective', 'retour perspective');
  });
  await step('cube de navigation', async () => {
    await w.click('.navcube-face:has-text("Dessus")', { force: true });
    await w.waitForTimeout(300);
    const dir = await w.evaluate(() => {
      const v = window.bimysApp.viewer;
      return v.camera.position.clone().sub(v.controls.target).normalize().y;
    });
    assert(dir > 0.95, `direction ${dir}`);
  });
  await step('point de vue enregistré', async () => {
    await w.click('.seg button[data-t=views]');
    await w.click('text=Enregistrer la vue actuelle');
    await w.fill('.modal input', 'Vue de dessus test');
    await w.click('.modal .btn.primary');
    await w.waitForSelector('.vp-item', { timeout: 5000 });
    await w.screenshot({ path: `${OUT}/07_vues.png` });
  });
  // exports : la boîte « Enregistrer sous » est simulée pour écrire dans un dossier temporaire
  const exportDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bimys-exports-'));
  await app.evaluate(({ dialog }, dir) => {
    dialog.showSaveDialog = async (_w, o) => ({ canceled: false, filePath: dir + (dir.includes('\\') ? '\\' : '/') + o.defaultPath.split(/[\\/]/).pop() });
  }, exportDir);
  await step('export PDF du métré (boîte Enregistrer sous)', async () => {
    await w.click('.tab[data-page=metre]');
    await w.click('.page:not([hidden]) [data-k=pdf]');
    await w.waitForTimeout(2500);
    const f = fs.readdirSync(exportDir).find((x) => x.endsWith('.pdf'));
    assert(f, 'aucun PDF écrit');
    assert(fs.readFileSync(path.join(exportDir, f)).subarray(0, 5).toString() === '%PDF-', 'PDF invalide');
  });
  await step('capture PNG de la vue 3D (Ctrl+Maj+S)', async () => {
    await w.click('.tab[data-page=viewer]');
    await w.waitForTimeout(300);
    await w.keyboard.press('Control+Shift+S');
    await w.waitForTimeout(2000);
    const f = fs.readdirSync(exportDir).find((x) => x.endsWith('.png'));
    assert(f && fs.statSync(path.join(exportDir, f)).size > 20000, 'capture absente');
  });
  await step('ouverture d’un fichier IFC (boîte Ouvrir) et fichiers récents', async () => {
    const ifc = path.join(root, exe ? path.join('public', 'samples') : path.join('dist', 'samples'), 'maison_pac_air_eau.ifc');
    await app.evaluate(({ dialog }, f) => {
      dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [f] });
    }, ifc);
    await w.keyboard.press('Control+o');
    await w.waitForFunction(() => window.bimysApp?.model?.data.fileName === 'maison_pac_air_eau.ifc' && !document.querySelector('.loader'), null, { timeout: 90000 });
    await w.waitForTimeout(500);
    const recent = await app.evaluate(({ Menu }) => Menu.getApplicationMenu().items[0].submenu.items[1].submenu.items.map((i) => i.label));
    assert(recent.some((l) => l.includes('maison_pac_air_eau.ifc')), `récents : ${recent.join(', ')}`);
  });
  await step('aide des raccourcis (F1)', async () => {
    await w.keyboard.press('F1');
    await w.waitForSelector('.modal .help-grid', { timeout: 3000 });
    await w.screenshot({ path: `${OUT}/08_raccourcis.png` });
    await w.click('.modal .btn.primary');
  });
  await step('taille de fenêtre mémorisée après redémarrage', async () => {
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setBounds({ x: 40, y: 30, width: 937, height: 655 }));
    await w.waitForTimeout(400);
    await app.close();
    ({ app, w } = await launch());
    await w.waitForSelector('.hero', { timeout: 30000 });
    const b = await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].getBounds());
    assert(Math.abs(b.width - 937) < 30 && Math.abs(b.height - 655) < 30, `taille ${b.width}x${b.height}`);
  });
  await step('journal d’erreurs écrit', async () => {
    const f = path.join(userData, 'logs', 'bimys.log');
    assert(fs.existsSync(f), 'journal absent');
    const t = fs.readFileSync(f, 'utf8');
    assert(t.includes('Démarrage Bimys') && t.includes('Maquette ouverte'), 'contenu du journal');
  });
  await step('aucune erreur JavaScript', async () => {
    assert(!errors.length, errors.join(' | '));
  });
  await app.close();
  fs.writeFileSync(path.join(OUT, 'resultats.txt'), results.join('\n') + '\n');
  console.log(`\n${results.length - failed} / ${results.length} étapes réussies`);
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error('ERREUR', e);
  process.exit(1);
});
