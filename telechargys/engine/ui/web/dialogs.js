'use strict';
/* Telechargys : fenêtres (ajout, lot, aspirateur, planificateur, réglages, propriétés). */

function catDir(id) {
  const c = S.categories.find(k => k.id === id);
  const base = S.settings.downloadDir || '';
  if (!c || !c.dir) return base;
  return /^([a-z]:[\\/]|[\\/])/i.test(c.dir) ? c.dir : joinPath(base, c.dir);
}
function catFor(name) {
  const e = ext(name);
  const c = S.categories.find(k => (k.exts || []).includes(e));
  return c ? c.id : 'other';
}
const catOpts = () => S.categories.map(c => [c.id, c.name]);
const queueOpts = () => S.queues.map(q => [q.id, q.name]);

function advancedFields(v) {
  const f = {
    referer: I({ value: v.referer || '', placeholder: 'https://…' }), cookies: I({ value: v.cookies || '', placeholder: 'nom=valeur; autre=valeur' }),
    userAgent: I({ value: v.userAgent || '', placeholder: 'Par défaut (réglages)' }), username: I({ value: v.username || '', autocomplete: 'off' }),
    password: I({ value: v.password || '', type: 'password', autocomplete: 'new-password' }),
    maxConn: Sel([['0', 'Par défaut (' + S.settings.maxConn + ')'], ...[1, 2, 4, 6, 8, 12, 16, 24, 32].map(n => [String(n), String(n)])], String(v.maxConn || 0)),
    limit: limitField(v.speedLimit || 0),
    algo: Sel([['', 'Aucune'], ['md5', 'MD5'], ['sha1', 'SHA-1'], ['sha256', 'SHA-256']], (v.checksum && v.checksum.algo) || v.checksumAlgo || ''),
    sum: I({ value: (v.checksum && v.checksum.expected) || '', placeholder: 'Empreinte attendue (facultatif)' }),
    description: I({ value: v.description || '' }),
  };
  const el = h('details', { class: 'adv' }, h('summary', {}, 'Options avancées'),
    h('div', { class: 'rowf' }, F('Connexions simultanées', f.maxConn), F('Limite de débit', f.limit)),
    F('Page d\'origine (Referer)', f.referer), F('Cookies', f.cookies),
    h('div', { class: 'rowf' }, F('Identifiant', f.username), F('Mot de passe', f.password)),
    F('Navigateur simulé (User-Agent)', f.userAgent),
    h('div', { class: 'rowf' }, F('Vérification d\'intégrité', f.algo), F('Empreinte', f.sum)),
    F('Note', f.description));
  el.values = () => ({
    referer: f.referer.value.trim(), cookies: f.cookies.value.trim(), userAgent: f.userAgent.value.trim(), username: f.username.value, password: f.password.value,
    maxConn: +f.maxConn.value, speedLimit: f.limit.val(), checksumAlgo: f.algo.value, checksum: f.sum.value.trim(), description: f.description.value.trim(),
  });
  return el;
}

// ---------- ajouter ----------
async function openAdd(pre) {
  pre = pre || {};
  if (!pre.url) {
    let clip = '';
    try { clip = A ? A.getClipboard() : E ? await E.readClipboard() : ''; } catch (e) {}
    if (/^(https?|ftp):\/\/\S+$/i.test((clip || '').trim())) pre = { url: clip.trim() };
  }
  const url = I({ value: pre.url || '', placeholder: 'https://exemple.com/fichier.zip', autofocus: true, inputMode: 'url', spellcheck: false });
  const name = I({ value: pre.fileName || '', placeholder: 'Détecté automatiquement', spellcheck: false });
  const cat = Sel(catOpts(), 'other'), queue = Sel(queueOpts(), 'main');
  const dir = I({ value: '', spellcheck: false });
  const quality = Sel([], ''), qf = F('Qualité vidéo', quality);
  qf.hidden = true;
  const info = h('div', { class: 'info', hidden: true });
  const adv = advancedFields(pre);
  let nameEdited = !!pre.fileName, dirEdited = false, catEdited = false, probed = null, seq = 0, timer = 0;
  name.oninput = () => { nameEdited = true; if (!catEdited) { cat.value = catFor(name.value); if (!dirEdited) dir.value = catDir(cat.value); } };
  cat.onchange = () => { catEdited = true; if (!dirEdited) dir.value = catDir(cat.value); };
  dir.oninput = () => { dirEdited = true; };
  dir.value = catDir(cat.value);
  const req = () => ({ url: url.value.trim(), ...adv.values(), headers: pre.headers });
  async function probe() {
    const u = url.value.trim();
    if (!/^(https?|ftp):\/\//i.test(u)) { info.hidden = true; return; }
    const my = ++seq;
    info.hidden = false; info.className = 'info'; info.innerHTML = '<span><span class="spin"></span> Analyse de l\'adresse…</span>';
    try {
      const p = await api('POST', 'probe', req());
      if (my !== seq) return;
      probed = p;
      if (!nameEdited) name.value = p.fileName;
      if (!catEdited) cat.value = catFor(name.value);
      if (!dirEdited) dir.value = catDir(cat.value);
      const type = p.kind === 'hls' ? 'Flux vidéo (' + (/\.mpd/i.test(p.url) || (p.mimeType || '').includes('dash') ? 'DASH' : 'HLS') + ')' : p.kind === 'ftp' ? 'FTP' : (ext(p.fileName) || 'fichier').toUpperCase();
      info.replaceChildren(h('span', {}, 'Taille : ', h('b', {}, p.size > 0 ? fmtSize(p.size) : 'inconnue')), h('span', {}, 'Type : ', h('b', {}, type)),
        h('span', {}, 'Reprise : ', h('b', {}, p.resumable ? 'oui' : 'non')), p.resumable && p.kind === 'http' ? h('span', {}, 'Accélération : ', h('b', {}, 'multi-connexions')) : '');
      if (p.variants && p.variants.length) {
        quality.replaceChildren(...p.variants.map((v, i) => h('option', { value: String(i) }, v.label)));
        qf.hidden = false;
      } else qf.hidden = true;
      if (/html/.test(p.mimeType || '') && p.kind === 'http') { info.append(h('span', {}, '⚠ Cette adresse renvoie une page web, pas un fichier.')); }
    } catch (e) {
      if (my !== seq) return;
      probed = null; info.className = 'info bad'; info.textContent = 'Analyse impossible : ' + e.message + '. Tu peux quand même lancer le téléchargement.';
    }
  }
  url.oninput = () => { clearTimeout(timer); timer = setTimeout(probe, 500); };
  async function submit(start) {
    const r = req();
    if (!/^(https?|ftp):\/\//i.test(r.url)) { toast('Adresse invalide (http, https ou ftp).', 'err'); return false; }
    r.fileName = nameEdited || probed ? name.value.trim() : '';
    r.category = cat.value; r.dir = dir.value.trim(); r.queue = queue.value; r.start = start;
    if (probed && probed.size > 0) r.size = probed.size;
    if (probed && probed.variants && probed.variants.length) { const v = probed.variants[+quality.value || 0]; r.variantUrl = v.url; r.audioUrl = v.audioUrl; r.quality = v.label; }
    try { await api('POST', 'downloads', r); } catch (e) {
      if (e.status !== 409) throw e;
      const old = S.dls.get(e.data.duplicate);
      const again = await askDuplicate(old);
      if (again === 'show') { m.close(); setFilter('all'); select(e.data.duplicate); return false; }
      if (again !== 'again') return false;
      r.allowDup = true;
      await api('POST', 'downloads', r);
    }
    if (!start) toast('Ajouté à la file « ' + (S.queues.find(q => q.id === r.queue) || {}).name + ' ».');
  }
  const later = h('button', { class: 'btn' }, 'Plus tard');
  const m = modal({
    title: 'Nouveau téléchargement',
    body: [F('Adresse', url), info, F('Nom du fichier', name), qf,
      h('div', { class: 'rowf' }, F('Catégorie', cat), F('File d\'attente', queue)),
      shell.android ? null : F('Enregistrer dans', folderField(dir)), adv],
    ok: 'Télécharger', onok: () => submit(true), extra: later,
  });
  later.onclick = async () => { try { if (await submit(false) !== false) m.close(); } catch (e) { fail(e); } };
  if (pre.url) probe();
}

// doublon : comme IDM, on demande quoi faire
function askDuplicate(old) {
  return new Promise(res => {
    let done = false;
    const end = v => { if (!done) { done = true; res(v); } };
    const st = old ? (STATUS[old.status] || old.status).toLowerCase() : '';
    const show = h('button', { class: 'btn' }, 'Voir l\'existant');
    const dm = modal({
      title: 'Lien déjà présent',
      body: h('p', {}, old ? `« ${old.fileName} » est déjà dans la liste (${st}). Le télécharger à nouveau ?` : 'Ce lien est déjà dans la liste. Le télécharger à nouveau ?'),
      ok: 'Télécharger à nouveau', onok: () => end('again'), extra: show, onclose: () => end('cancel'),
    });
    show.onclick = () => { end('show'); dm.close(); };
  });
}

// ---------- actualiser l'adresse ----------
function openRefresh(d) {
  const u = I({ value: d.url, autofocus: true, spellcheck: false });
  api('POST', `downloads/${d.id}/refreshwait`, { on: true }).catch(() => {});
  const how = shell.android
    ? 'ou retourne sur la page d\'origine et « Partage » à nouveau le lien vers Telechargys (ou ouvre-le dans le navigateur intégré).'
    : 'ou retourne sur la page d\'origine dans ton navigateur et clique à nouveau sur le lien de téléchargement : Telechargys récupérera la nouvelle adresse tout seul.';
  const m = modal({
    title: 'Actualiser l\'adresse',
    body: [h('p', { class: 'hint', style: 'margin:0 0 10px' }, 'Quand un lien a expiré, colle ici la nouvelle adresse du même fichier, ' + how + ' Le téléchargement reprendra là où il s\'était arrêté.'),
      h('div', { class: 'info' }, h('span', { html: '<span class="spin"></span> En attente d\'un nouveau clic sur le lien…' })), F('Nouvelle adresse', u)],
    ok: 'Actualiser et reprendre',
    onok: async () => { await api('POST', `downloads/${d.id}/refresh`, { url: u.value.trim() }); await api('POST', `downloads/${d.id}/start`, {}); },
    onclose: () => api('POST', `downloads/${d.id}/refreshwait`, { on: false }).catch(() => {}),
  });
  m.dataset.refresh = d.id;
}

// ---------- propriétés ----------
function openProps(d) {
  const run = d.status === 'downloading' || d.status === 'merging';
  const name = I({ value: d.fileName, disabled: run }), dir = I({ value: d.dir, disabled: run || shell.android });
  const cat = Sel(catOpts(), d.category), queue = Sel(queueOpts(), d.queue);
  const adv = advancedFields(d); adv.open = true;
  const hashBtn = d.status === 'completed' ? h('button', { class: 'btn small', onclick: async () => { hashBtn.disabled = true; try { const r = await api('POST', `downloads/${d.id}/hash`, { algo: 'sha256' }); shell.copy(r.hash); toast(r.hash, '', 'SHA-256 (copié)'); } catch (e) { fail(e); } hashBtn.disabled = false; } }, 'Calculer le SHA-256') : null;
  modal({
    title: 'Propriétés',
    body: [F('Adresse', h('div', { class: 'inbtn' }, I({ value: d.url, readOnly: true }), h('button', { class: 'btn', html: icon('copy'), onclick: () => shell.copy(d.url) }))),
      F('Nom du fichier', name, run ? 'Mets en pause pour renommer ou déplacer.' : ''), F('Dossier', folderField(dir)),
      h('div', { class: 'rowf' }, F('Catégorie', cat), F('File d\'attente', queue)),
      h('dl', { class: 'kv', style: 'margin-bottom:12px' }, [['Taille', d.size > 0 ? fmtSize(d.size) + ' (' + d.size.toLocaleString('fr-FR') + ' octets)' : 'inconnue'], ['Ajouté', fmtDate(d.addedAt)], d.completedAt ? ['Terminé', fmtDate(d.completedAt)] : null,
        ['Durée', fmtEta((d.elapsedMs || 0) / 1000) || '0 s'], d.mimeType ? ['Type', d.mimeType] : null].filter(Boolean).map(([k, v]) => [h('dt', {}, k), h('dd', {}, v)])),
      hashBtn, adv],
    ok: 'Enregistrer',
    onok: () => api('POST', `downloads/${d.id}/update`, { fileName: name.value.trim(), dir: dir.value.trim(), category: cat.value, queue: queue.value, ...adv.values() }),
  });
}

// ---------- limiteur global ----------
function openLimit() {
  const on = h('input', { type: 'checkbox', checked: !!S.settings.speedLimitOn });
  const lim = limitField(S.settings.speedLimit || 1048576);
  modal({
    title: 'Limiteur de débit',
    body: [h('label', { class: 'check' }, on, 'Limiter le débit total des téléchargements'), F('Débit maximum', lim), h('p', { class: 'hint' }, 'Utile pour garder de la bande passante pour le reste (visio, streaming…).')],
    ok: 'Appliquer', onok: () => api('PUT', 'settings', { speedLimitOn: on.checked && lim.val() > 0, speedLimit: lim.val() }),
  });
}

// ---------- lot ----------
function openBatch(text, ctx) {
  ctx = ctx || {};
  const pat = I({ placeholder: 'https://site.com/photo[001-120].jpg', spellcheck: false });
  const list = h('textarea', { class: 'in', rows: 8, placeholder: 'Une adresse par ligne…', spellcheck: false }, text || '');
  const cnt = h('div', { class: 'hint' });
  const queue = Sel(queueOpts(), 'main');
  const start = h('input', { type: 'checkbox', checked: true });
  const urls = () => [...new Set(list.value.split(/\s+/).map(s => s.trim()).filter(s => /^(https?|ftp):\/\//i.test(s)))];
  const upd = () => { const n = urls().length; cnt.textContent = n ? `${n} adresse${n > 1 ? 's' : ''} reconnue${n > 1 ? 's' : ''}` : 'Aucune adresse reconnue'; };
  list.oninput = upd; upd();
  const gen = h('button', { class: 'btn', onclick: async () => { try { const r = await api('POST', 'batch', { pattern: pat.value }); list.value = (list.value.trim() ? list.value.trim() + '\n' : '') + r.urls.join('\n'); upd(); } catch (e) { fail(e); } } }, 'Générer');
  const imp = h('input', { type: 'file', accept: '.txt,text/plain', hidden: true, onchange: async () => { if (imp.files[0]) { list.value += '\n' + await imp.files[0].text(); upd(); } } });
  modal({
    title: ctx.urls ? 'Liens envoyés par le navigateur' : 'Téléchargement par lot', wide: true,
    body: [F('Motif numéroté', h('div', { class: 'inbtn noenter' }, pat, gen), 'Exemples : [1-50], [001-120] (avec zéros), [a-f], [0-100:10] (de 10 en 10).'),
      F('Liste d\'adresses', list), cnt, imp,
      h('div', { class: 'rowf' }, F('File d\'attente', queue), h('div', {}, h('label', { class: 'check', style: 'margin-top:22px' }, start, 'Démarrer la file tout de suite')))],
    extra: h('button', { class: 'btn', onclick: () => imp.click() }, 'Importer un fichier .txt'),
    ok: 'Ajouter à la file',
    onok: async () => {
      const u = urls(); if (!u.length) { toast('Aucune adresse à ajouter.', 'err'); return false; }
      const added = (await api('POST', 'downloads', { items: u.map(x => ({ url: x, queue: queue.value, referer: ctx.referer || '', cookies: ctx.cookies || '', userAgent: ctx.userAgent || '' })) })) || [];
      if (start.checked) await api('POST', `queues/${queue.value}/start`, {}).catch(() => {});
      const skip = u.length - added.length;
      toast(`${added.length} téléchargement${added.length > 1 ? 's' : ''} ajouté${added.length > 1 ? 's' : ''}.` + (skip ? ` ${skip} déjà dans la liste.` : ''));
    },
  });
}

// ---------- aspirateur de site ----------
function openGrab() {
  const url = I({ placeholder: 'https://exemple.com/galerie', autofocus: true, inputMode: 'url', spellcheck: false });
  const depth = Sel([['0', 'Cette page uniquement'], ['1', 'Page + liens (1 niveau)'], ['2', '2 niveaux'], ['3', '3 niveaux']], '0');
  const same = h('input', { type: 'checkbox', checked: true });
  const types = S.categories.filter(c => c.id !== 'other').map(c => { const cb = h('input', { type: 'checkbox', checked: true }); cb._c = c; return cb; });
  const out = h('div', {}), stat = h('div', { class: 'hint' });
  const queue = Sel(queueOpts(), 'main');
  let job = null, items = [], poll = 0, checked = new Set();
  const go = h('button', { class: 'btn primary noenter' }, 'Explorer');
  function draw() {
    const all = h('input', { type: 'checkbox', checked: items.length > 0 && checked.size === items.length, onchange: () => { checked = new Set(all.checked ? items.map(i => i.url) : []); draw(); } });
    out.replaceChildren(items.length ? h('div', { class: 'scroll' }, h('table', { class: 'tbl' },
      h('thead', {}, h('tr', {}, h('th', {}, all), h('th', {}, 'Fichier'), h('th', {}, 'Type'), h('th', {}, 'Adresse'))),
      h('tbody', {}, items.map(i => h('tr', {}, h('td', {}, h('input', { type: 'checkbox', checked: checked.has(i.url), onchange: e => { e.target.checked ? checked.add(i.url) : checked.delete(i.url); m.okBtn.textContent = `Télécharger (${checked.size})`; } })),
        h('td', { title: i.text || i.name }, i.name), h('td', {}, i.ext.toUpperCase()), h('td', { title: i.url }, i.url)))))) : '');
    m.okBtn.textContent = `Télécharger (${checked.size})`;
  }
  async function tick() {
    try {
      const j = await api('GET', 'grab/' + job);
      const fresh = j.items.slice(items.length); items = j.items; fresh.forEach(i => checked.add(i.url));
      stat.innerHTML = j.done ? '' : '<span class="spin"></span> ';
      stat.append(`${j.pages} page${j.pages > 1 ? 's' : ''} explorée${j.pages > 1 ? 's' : ''}, ${items.length} fichier${items.length > 1 ? 's' : ''} trouvé${items.length > 1 ? 's' : ''}` + (j.error ? ' · ' + j.error : '') + (j.done ? ' · terminé' : ''));
      if (fresh.length || j.done) draw();
      if (j.done) { clearInterval(poll); go.disabled = false; go.textContent = 'Explorer'; }
    } catch (e) { clearInterval(poll); go.disabled = false; }
  }
  go.onclick = async () => {
    try {
      const exts = types.filter(t => t.checked).flatMap(t => t._c.exts);
      const r = await api('POST', 'grab', { url: url.value.trim(), depth: +depth.value, sameDomain: same.checked, exts });
      job = r.id; items = []; checked = new Set(); draw(); go.disabled = true; go.textContent = 'Exploration…';
      clearInterval(poll); poll = setInterval(tick, 700);
    } catch (e) { fail(e); }
  };
  const m = modal({
    title: 'Aspirateur de site', wide: true,
    body: [F('Adresse de la page', h('div', { class: 'inbtn' }, url, go)),
      h('div', { class: 'rowf' }, F('Profondeur', depth), h('div', {}, h('label', { class: 'check', style: 'margin-top:22px' }, same, 'Rester sur le même site'))),
      F('Types de fichiers', h('div', { class: 'days' }, types.map(t => h('label', {}, t, t._c.name)))), stat, out,
      F('File d\'attente', queue)],
    ok: 'Télécharger (0)',
    onok: async () => {
      if (!checked.size) { toast('Coche au moins un fichier.', 'err'); return false; }
      await api('POST', 'downloads', { items: [...checked].map(u => ({ url: u, queue: queue.value, referer: url.value.trim() })) });
      await api('POST', `queues/${queue.value}/start`, {}).catch(() => {});
      toast(`${checked.size} fichier${checked.size > 1 ? 's' : ''} ajouté${checked.size > 1 ? 's' : ''} à la file.`);
    },
    onclose: () => { clearInterval(poll); if (job) api('DELETE', 'grab/' + job).catch(() => {}); },
  });
}

// ---------- files d'attente et planificateur ----------
const DAYS = [[1, 'Lun'], [2, 'Mar'], [3, 'Mer'], [4, 'Jeu'], [5, 'Ven'], [6, 'Sam'], [0, 'Dim']];
function openQueues() {
  let qs = JSON.parse(JSON.stringify(S.queues));
  const box = h('div', {});
  const save = () => api('PUT', 'queues', qs);
  function draw() {
    box.replaceChildren(...qs.map((q, idx) => {
      const live = S.queues.find(x => x.id === q.id), running = live && live.running;
      const waiting = [...S.dls.values()].filter(d => d.queue === q.id && d.status === 'queued').length;
      const s = q.schedule = q.schedule || { enabled: false, start: '02:00', stop: '', days: [] };
      const name = I({ value: q.name, oninput: e => { q.name = e.target.value; } });
      const max = Sel([1, 2, 3, 4, 5, 6, 8, 10].map(n => [String(n), n + ' à la fois']), String(q.maxActive)); max.onchange = () => { q.maxActive = +max.value; };
      const en = h('input', { type: 'checkbox', checked: s.enabled, onchange: e => { s.enabled = e.target.checked; draw(); } });
      const st = I({ type: 'time', value: s.start || '02:00', oninput: e => { s.start = e.target.value; } });
      const sp = I({ type: 'time', value: s.stop || '', oninput: e => { s.stop = e.target.value; } });
      const days = h('div', { class: 'days' }, DAYS.map(([n, l]) => h('label', {}, h('input', { type: 'checkbox', checked: (s.days || []).includes(n), onchange: e => { s.days = (s.days || []).filter(x => x !== n); if (e.target.checked) s.days.push(n); } }), l)));
      const post = Sel([['', 'Ne rien faire'], ...(shell.desktop ? [['exit', 'Quitter Telechargys'], ['sleep', 'Mettre l\'ordinateur en veille'], ['hibernate', 'Veille prolongée'], ['shutdown', 'Éteindre l\'ordinateur']] : [])], q.postAction || ''); post.onchange = () => { q.postAction = post.value; };
      return h('div', { class: 'card' },
        h('h4', {}, running ? h('span', { class: 'st downloading' }, 'En cours') : h('span', { class: 'st' }, 'Arrêtée'), h('span', { class: 'grow' }), h('span', { class: 'hint', style: 'margin:0' }, `${waiting} en attente`),
          h('button', { class: 'btn small ' + (running ? '' : 'primary'), onclick: async () => { try { await save(); await api('POST', `queues/${q.id}/${running ? 'stop' : 'start'}`, {}); setTimeout(draw, 250); } catch (e) { fail(e); } } }, running ? 'Arrêter' : 'Démarrer'),
          q.id !== 'main' ? h('button', { class: 'btn small danger', html: icon('trash'), title: 'Supprimer cette file', onclick: () => { qs.splice(idx, 1); draw(); } }) : null),
        h('div', { class: 'rowf' }, F('Nom', name), F('Téléchargements simultanés', max)),
        h('label', { class: 'check' }, en, 'Planifier cette file'),
        s.enabled ? [h('div', { class: 'rowf' }, F('Démarrer à', st), F('Arrêter à (facultatif)', sp)), F('Jours (aucun coché = tous les jours)', days)] : null,
        shell.desktop ? F('Quand la file est terminée', post) : null);
    }), h('button', { class: 'btn', html: icon('plus'), onclick: () => { qs.push({ id: '', name: 'Nouvelle file', maxActive: 2, schedule: { enabled: false, start: '02:00', stop: '', days: [] }, postAction: '' }); draw(); } }, 'Nouvelle file'));
  }
  draw();
  modal({ title: 'Files d\'attente et planificateur', wide: true, body: [h('p', { class: 'hint', style: 'margin:0 0 10px' }, 'Une file télécharge ses fichiers les uns après les autres. Tu peux la lancer à la main ou à heure fixe (la nuit par exemple). L\'application doit rester ouverte.'), box], ok: 'Enregistrer', onok: save });
}

// ---------- réglages ----------
function openSettings(tab) {
  const s = JSON.parse(JSON.stringify(S.settings));
  let cats = JSON.parse(JSON.stringify(S.categories));
  const chk = (k, label) => h('label', { class: 'check' }, h('input', { type: 'checkbox', checked: !!s[k], onchange: e => { s[k] = e.target.checked; } }), label);
  const num = (k, min, max) => I({ type: 'number', min, max, value: s[k], oninput: e => { s[k] = Math.max(min, Math.min(max, +e.target.value || min)); } });
  const txt = (k, ph) => I({ value: s[k] || '', placeholder: ph || '', spellcheck: false, oninput: e => { s[k] = e.target.value; } });
  const dirIn = txt('downloadDir');
  const theme = Sel([['auto', 'Automatique (système)'], ['light', 'Clair'], ['dark', 'Sombre']], s.theme || 'auto'); theme.onchange = () => { s.theme = theme.value; };
  const dup = Sel([['rename', 'Renommer : fichier (1).zip'], ['overwrite', 'Remplacer le fichier existant']], s.onDuplicate || 'rename'); dup.onchange = () => { s.onDuplicate = dup.value; };
  const maxc = Sel([1, 2, 4, 6, 8, 12, 16, 24, 32].map(n => [String(n), String(n)]), String(s.maxConn)); maxc.onchange = () => { s.maxConn = +maxc.value; };
  const capExts = h('textarea', { class: 'in', rows: 3, oninput: e => { s.captureExts = e.target.value.split(/[\s,;]+/).map(x => x.replace(/^\./, '').toLowerCase()).filter(Boolean); } }, (s.captureExts || []).join(' '));

  const panes = {
    general: ['Général', () => [
      F('Thème', theme),
      shell.android ? h('p', { class: 'hint' }, 'Les fichiers sont enregistrés dans Téléchargements/Telechargys, rangés par catégorie.') : F('Dossier de téléchargement', folderField(dirIn), 'Chaque catégorie y a son sous-dossier.'),
      F('Si le fichier existe déjà', dup),
      chk('showAddDialog', 'Afficher la fenêtre « Nouveau téléchargement » pour chaque lien capté'),
      chk('notifyDone', 'Notification quand un téléchargement est terminé'),
      shell.android ? null : chk('soundDone', 'Petit son à la fin d\'un téléchargement'),
      chk('autoResume', 'Reprendre automatiquement les téléchargements interrompus au lancement'),
      shell.desktop ? [chk('showProgressWin', 'Ouvrir une fenêtre de progression pour chaque téléchargement'), chk('showDoneWin', 'Afficher la fenêtre « Téléchargement terminé »')] : null,
      shell.desktop ? [chk('clipboardWatch', 'Surveiller le presse-papiers (proposer les liens copiés)'), chk('startWithSystem', 'Lancer Telechargys au démarrage de Windows'), chk('minimizeToTray', 'Garder l\'application dans la zone de notification à la fermeture')] : null,
      shell.android ? chk('wifiOnly', 'Télécharger uniquement en Wi-Fi') : null,
    ]],
    net: ['Connexion', () => [
      h('div', { class: 'rowf' }, F('Connexions par fichier', maxc, 'Plus il y en a, plus ça va vite (8 est un bon réglage, 32 au maximum).'), F('Connexions par flux vidéo HLS', num('hlsConn', 1, 16))),
      h('div', { class: 'rowf' }, F('Tentatives en cas d\'échec', num('retries', 0, 100)), F('Attente entre deux tentatives (s)', num('retryWaitSec', 1, 600)), F('Délai d\'inactivité (s)', num('timeoutSec', 5, 600))),
      F('Proxy', txt('proxy', 'http://hote:port ou socks5://hote:port'), 'Laisse vide pour une connexion directe.'),
      F('Navigateur simulé (User-Agent)', txt('userAgent')),
      F('Relancer automatiquement les téléchargements en erreur', (() => { const x = Sel([['0', 'Jamais'], ['1', 'Après 1 minute'], ['5', 'Après 5 minutes'], ['15', 'Après 15 minutes'], ['60', 'Après 1 heure']], String(s.autoRetryMin || 0)); x.onchange = () => { s.autoRetryMin = +x.value; }; return x; })(), 'Utile pour les coupures réseau et les serveurs saturés (5 essais au maximum).'),
      chk('hlsToMp4', 'Convertir les flux vidéo HLS / DASH en fichier MP4 (sans réencodage)'),
    ]],
    cats: ['Catégories', () => {
      const box = h('div', {});
      const draw = () => box.replaceChildren(...cats.map((c, i) => h('div', { class: 'card' },
        h('div', { class: 'rowf' }, F('Nom', I({ value: c.name, oninput: e => { c.name = e.target.value; } })), shell.android ? null : F('Dossier', folderField(I({ value: c.dir, placeholder: '(dossier de base)', oninput: e => { c.dir = e.target.value; } })))),
        c.id === 'other' ? h('p', { class: 'hint', style: 'margin:0' }, 'Reçoit tous les fichiers qui ne vont dans aucune autre catégorie.') : F('Extensions', I({ value: (c.exts || []).join(' '), spellcheck: false, oninput: e => { c.exts = e.target.value.split(/[\s,;]+/).filter(Boolean); } })),
        !['video', 'music', 'archive', 'program', 'document', 'image', 'other'].includes(c.id) ? h('button', { class: 'btn small danger', onclick: () => { cats.splice(i, 1); draw(); } }, 'Supprimer') : null)),
        h('button', { class: 'btn', html: icon('plus'), onclick: () => { cats.splice(cats.length - 1, 0, { id: '', name: 'Nouvelle catégorie', dir: 'Nouvelle catégorie', exts: [] }); draw(); } }, 'Nouvelle catégorie'));
      draw(); return box;
    }],
    sites: ['Sites', () => {
      const box = h('div', {});
      s.logins = s.logins || [];
      const draw = () => box.replaceChildren(h('p', { class: 'hint', style: 'margin:0 0 10px' }, 'Identifiants envoyés automatiquement aux sites qui demandent un mot de passe (authentification HTTP).'),
        ...s.logins.map((l, i) => h('div', { class: 'card rowf' }, I({ value: l.host, placeholder: 'exemple.com', oninput: e => { l.host = e.target.value.trim(); } }), I({ value: l.username, placeholder: 'Identifiant', oninput: e => { l.username = e.target.value; } }),
          I({ value: l.password, type: 'password', placeholder: 'Mot de passe', oninput: e => { l.password = e.target.value; } }), h('button', { class: 'btn danger', style: 'flex:none', html: icon('trash'), onclick: () => { s.logins.splice(i, 1); draw(); } }))),
        h('button', { class: 'btn', html: icon('plus'), onclick: () => { s.logins.push({ host: '', username: '', password: '' }); draw(); } }, 'Ajouter un site'));
      draw(); return box;
    }],
    capture: [shell.android ? 'Capture' : 'Navigateur', () => [
      shell.android
        ? h('div', { class: 'info' }, h('span', {}, 'Sur téléphone : utilise « Partager » depuis n\'importe quelle appli ou le navigateur intégré (menu), qui repère les vidéos et les fichiers des pages.'))
        : h('div', { class: 'info' }, h('span', { html: 'Pour capter les téléchargements de Chrome, Edge ou Firefox, installe l\'extension fournie dans le dossier <b>extension</b> (voir le menu Aide du programme). Elle se connecte toute seule et te demandera une autorisation ici.' })),
      F('Types de fichiers captés automatiquement', capExts, 'Extensions séparées par des espaces.'),
      shell.android ? null : [
        F('Sites exclus de la capture', h('textarea', { class: 'in', rows: 2, placeholder: 'exemple.com autre-site.fr', oninput: e => { s.captureExclude = e.target.value.split(/[\s,;]+/).map(x => x.trim().toLowerCase()).filter(Boolean); } }, (s.captureExclude || []).join(' ')), 'Les téléchargements de ces sites restent dans le navigateur. Astuce : maintiens Alt en cliquant sur un lien pour ne pas le capter.'),
        chk('videoButton', 'Afficher le bouton « Télécharger cette vidéo » sur les vidéos des pages')],
      shell.desktop ? F('Analyse après téléchargement (antivirus)', txt('antivirusCmd', '"C:\\Program Files\\Windows Defender\\MpCmdRun.exe" -Scan -ScanType 3 -File %f'), 'Commande lancée sur chaque fichier terminé ; %f est remplacé par le chemin du fichier.') : null,
    ]],
    data: ['Sauvegarde', () => [
      h('p', { class: 'hint', style: 'margin:0 0 10px' }, 'La sauvegarde contient les réglages, les catégories, les files et la liste des téléchargements (pas les fichiers eux-mêmes).'),
      h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px' },
        h('button', { class: 'btn', onclick: () => saveExport('export', 'telechargys-sauvegarde.json') }, 'Exporter une sauvegarde (JSON)'),
        h('button', { class: 'btn', onclick: () => impIn.click() }, 'Restaurer une sauvegarde…'),
        h('button', { class: 'btn', onclick: () => saveExport('export.csv', 'telechargys-historique.csv') }, 'Exporter l\'historique (CSV)'),
        h('button', { class: 'btn', onclick: () => saveExport('export.txt', 'telechargys-adresses.txt') }, 'Exporter les adresses (.txt)')),
      impIn,
      h('button', { class: 'btn danger', onclick: () => act('removeCompleted', []).then(() => toast('Liste nettoyée.')) }, 'Effacer les téléchargements terminés de la liste'),
      h('p', { class: 'hint', style: 'margin-top:18px' }, `Telechargys ${S.version} · QMTech`),
    ]],
  };
  const impIn = h('input', { type: 'file', accept: '.json,application/json', hidden: true, onchange: async () => { try { const r = await api('POST', 'import', JSON.parse(await impIn.files[0].text())); toast(`Sauvegarde restaurée (${r.imported} téléchargement${r.imported > 1 ? 's' : ''} ajouté${r.imported > 1 ? 's' : ''}).`); m.close(); } catch (e) { fail(new Error('Sauvegarde illisible : ' + e.message)); } } });
  const content = h('div', {}), tabs = h('div', { class: 'tabs' });
  const built = {};
  function show(k) {
    $$('button', tabs).forEach(b => b.classList.toggle('on', b.dataset.k === k));
    if (!built[k]) built[k] = h('div', {}, panes[k][1]());
    content.replaceChildren(built[k]);
  }
  for (const k in panes) tabs.append(h('button', { 'data-k': k, onclick: () => show(k) }, panes[k][0]));
  const m = modal({
    title: 'Réglages', wide: true, body: [tabs, content], ok: 'Enregistrer',
    onok: async () => { await api('PUT', 'settings', s); if (built.cats) await api('PUT', 'categories', cats); shell.apply(s); },
  });
  show(tab && panes[tab] ? tab : 'general');
}
async function saveExport(path, name) {
  try {
    const r = await fetch('/api/' + path, { headers: { 'X-Token': TOKEN } });
    const text = await r.text();
    if (A && A.saveText) { toast('Enregistré : ' + A.saveText(name, text)); return; }
    const a = h('a', { href: URL.createObjectURL(new Blob([text], { type: 'application/octet-stream' })), download: name });
    document.body.append(a); a.click(); a.remove();
  } catch (e) { fail(e); }
}
