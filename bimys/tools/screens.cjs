// Captures d'écran et exports PDF en navigateur headless (Playwright).
// Usage : npx vite build && node tools/screens.cjs [dossier_sortie]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const OUT = path.resolve(process.argv[2] || 'screenshots');
fs.mkdirSync(OUT, { recursive: true });

async function waitServer(url, ms = 20000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error('serveur indisponible');
}

(async () => {
  const srv = spawn('npx', ['vite', 'preview', '--port', '4179', '--strictPort'], { cwd: path.resolve(__dirname, '..'), stdio: 'ignore' });
  const base = 'http://localhost:4179/';
  const errors = [];
  try {
    await waitServer(base);
    const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
    for (const dev of [
      { name: 'pc', viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
      { name: 'tel', viewport: { width: 412, height: 870 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
    ]) {
      const ctx = await browser.newContext({ viewport: dev.viewport, deviceScaleFactor: dev.deviceScaleFactor, isMobile: dev.isMobile, hasTouch: dev.hasTouch, acceptDownloads: true, locale: 'fr-FR' });
      const page = await ctx.newPage();
      page.on('console', (m) => m.type() === 'error' && errors.push(`[${dev.name}] ${m.text()}`));
      page.on('pageerror', (e) => errors.push(`[${dev.name}] ${e.message}`));
      await page.goto(base);
      await page.waitForSelector('.hero');
      await page.screenshot({ path: `${OUT}/${dev.name}_01_accueil.png` });
      await page.click('[data-sample="maison_chaudiere_gaz.ifc"]');
      await page.waitForFunction(() => document.querySelector('.tab[data-page=metre]') && !document.querySelector('.tab[data-page=metre]').disabled && !document.querySelector('.loader'), null, { timeout: 60000 });
      await page.waitForTimeout(800);
      await page.screenshot({ path: `${OUT}/${dev.name}_02_vue3d.png` });
      if (dev.name === 'pc') {
        // sélection d'un radiateur via l'arborescence
        await page.evaluate(() => {
          const app = window.bimysApp;
          const rad = app.model.elements.find((e) => e.name === 'Radiateur séjour 1');
          app.showElement(rad.id);
        });
        await page.waitForTimeout(500);
        await page.screenshot({ path: `${OUT}/${dev.name}_03_selection.png` });
        await page.click('.seg button[data-t=lots]');
        await page.click('[data-tool=ghost]');
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${dev.name}_04_lots_transparence.png` });
        await page.click('[data-tool=cut]');
        await page.selectOption('[data-k=level]', '1');
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/${dev.name}_05_coupe_r1.png` });
        await page.click('[data-k=reset]');
        await page.click('[data-k=close]');
        await page.click('[data-tool=ghost]');
      }
      const tabs = ['metre', 'nomenclature', 'deperditions', 'coherence', 'maintenance', 'energie', 'defis', 'settings'];
      let i = 6;
      for (const t of tabs) {
        if (t === 'settings') await page.click('.top-actions .icon-btn[title=Paramètres]');
        else await page.click(`.tab[data-page=${t}]`);
        await page.waitForTimeout(400);
        if (t === 'deperditions') {
          await page.click('.room[data-gid] .room-head >> nth=1');
          await page.waitForTimeout(200);
        }
        await page.screenshot({ path: `${OUT}/${dev.name}_${String(i).padStart(2, '0')}_${t}.png`, fullPage: false });
        i++;
      }
      if (dev.name === 'pc') {
        // exports PDF
        const grab = async (tab, sel, name) => {
          await page.click(`.tab[data-page=${tab}]`);
          await page.waitForTimeout(300);
          const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.click(`.page:not([hidden]) ${sel}`)]);
          await dl.saveAs(`${OUT}/${name}`);
        };
        await grab('metre', '[data-k=pdf]', 'export_metre.pdf');
        await grab('metre', '[data-k=csv]', 'export_metre.csv');
        await grab('nomenclature', '[data-k=pdf]', 'export_nomenclature.pdf');
        await grab('deperditions', '.toolbar [data-k=pdf]', 'export_deperditions.pdf');
        await grab('coherence', '[data-k=pdf]', 'export_coherence.pdf');
        await grab('energie', '[data-k=pdf]', 'export_energie.pdf');
        // intervention de maintenance signée
        await page.click('.tab[data-page=maintenance]');
        await page.click('[data-a=new]');
        await page.fill('[data-f=intervenant]', 'Élève test');
        await page.click('.tri button[data-v=ok] >> nth=0');
        await page.click('.tri button[data-v=nok] >> nth=1');
        await page.fill('[data-f=observations]', 'Analyse de combustion conforme. Siphon nettoyé.');
        const pad = await page.$('.sig-pad');
        const b = await pad.boundingBox();
        await page.mouse.move(b.x + 20, b.y + 80);
        await page.mouse.down();
        for (let k = 0; k < 30; k++) await page.mouse.move(b.x + 20 + k * 10, b.y + 80 + Math.sin(k / 3) * 30);
        await page.mouse.up();
        await page.screenshot({ path: `${OUT}/pc_14_intervention.png` });
        const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.click('[data-k=savepdf]')]);
        await dl.saveAs(`${OUT}/export_intervention.pdf`);
        await page.waitForTimeout(400);
        await page.click('.tab[data-page=viewer]');
        await page.waitForTimeout(500);
        console.log('etat vue', JSON.stringify(await page.evaluate(() => { const v = window.bimysApp.viewer; return { lost: v.renderer.getContext().isContextLost(), planes: v.renderer.clippingPlanes.length, cam: v.camera.position.toArray(), tgt: v.controls.target.toArray(), w: v.container.clientWidth, markers: v.markers.children.length }; })));
        await page.click('[data-tool=iso]');
        await page.waitForTimeout(300);
        await page.screenshot({ path: `${OUT}/pc_15_reperes_maintenance.png` });
        // défi
        await page.click('.tab[data-page=defis]');
        await page.fill('[data-k=eleve]', 'Dupont Léa');
        await page.fill('[data-k=classe]', '1re ICCER');
        await page.fill('[data-k=seed]', '42');
        await page.click('[data-k=go]');
        await page.waitForTimeout(300);
        const inputs = await page.$$('.q input[type=text]');
        for (const inp of inputs) await inp.fill('3');
        await page.click('text=Valider mes réponses');
        await page.click('.modal .btn.primary').catch(() => {});
        await page.waitForTimeout(400);
        await page.screenshot({ path: `${OUT}/pc_16_defi_resultat.png`, fullPage: true });
        const [dl2] = await Promise.all([page.waitForEvent('download', { timeout: 30000 }), page.click('text=Export PDF du résultat')]);
        await dl2.saveAs(`${OUT}/export_defi.pdf`);
      }
      await ctx.close();
    }
    // variante PAC
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(`[pac] ${e.message}`));
    await page.goto(base);
    await page.click('[data-sample="maison_pac_air_eau.ifc"]');
    await page.waitForFunction(() => !document.querySelector('.loader') && window.bimysApp?.model, null, { timeout: 60000 });
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/pac_01_vue3d.png` });
    await page.click('.tab[data-page=maintenance]');
    await page.click('text=PAC air/eau monobloc');
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}/pac_02_maintenance.png` });
    await browser.close();
  } finally {
    srv.kill();
  }
  fs.writeFileSync(`${OUT}/console_errors.txt`, errors.join('\n'));
  console.log(errors.length ? `ERREURS:\n${errors.join('\n')}` : 'Aucune erreur console.');
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
