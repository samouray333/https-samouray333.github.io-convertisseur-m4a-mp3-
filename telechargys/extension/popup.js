const api = typeof browser !== 'undefined' ? browser : chrome;
const $ = s => document.querySelector(s);
const ask = m => new Promise(r => api.runtime.sendMessage(m, r));
function size(n) { if (!n) return ''; const u = ['o', 'Ko', 'Mo', 'Go']; let i = 0; while (n >= 1024 && i < 3) { n /= 1024; i++; } return n.toFixed(i ? 1 : 0).replace('.', ',') + ' ' + u[i]; }
function el(tag, props, ...kids) { const e = Object.assign(document.createElement(tag), props || {}); e.append(...kids); return e; }

async function refresh() {
  const [tab] = await api.tabs.query({ active: true, currentWindow: true });
  const s = await ask({ type: 'status', tabId: tab.id });
  $('#dot').className = 'dot' + (s.connected ? ' ok' : '');
  const st = $('#state'); st.replaceChildren();
  $('#tog').hidden = !s.connected;
  if (!s.running) st.append(el('p', {}, 'L\'application Telechargys n\'est pas lancée.'), el('p', { className: 'mute' }, 'Ouvre-la sur cet ordinateur puis rouvre cette fenêtre.'));
  else if (!s.connected) {
    const b = el('button', { className: 'p' }, 'Connecter à Telechargys');
    b.onclick = async () => { b.disabled = true; b.textContent = 'Accepte la demande dans Telechargys…'; await ask({ type: 'pair' }); refresh(); };
    st.append(el('p', {}, 'L\'extension n\'est pas encore autorisée.'), b);
  }
  $('#enabled').checked = s.enabled;
  const box = $('#media'); box.replaceChildren();
  if (s.connected) {
    box.append(el('h4', {}, 'Vidéos et sons détectés sur cette page'));
    if (!s.media.length) box.append(el('p', { className: 'mute' }, 'Rien pour l\'instant. Lance la lecture de la vidéo, elle apparaîtra ici.'));
    for (const m of s.media) {
      let name = m.url; try { name = decodeURIComponent(new URL(m.url).pathname.split('/').pop()) || m.url; } catch (e) {}
      const b = el('button', { className: 'p' }, 'Télécharger');
      b.onclick = async () => {
        b.disabled = true;
        const title = (tab.title || '').replace(/[<>:"/\\|?*]/g, ' ').trim().slice(0, 80);
        const r = await ask({ type: 'send', url: m.url, referer: tab.url, fileName: m.type === 'HLS' && title ? title + '.mp4' : '' });
        b.textContent = r && r.error ? 'Échec' : 'Envoyé ✓'; if (r && r.error) b.title = r.error;
      };
      box.append(el('div', { className: 'm' }, el('span', { className: 'tag' }, m.type), el('div', {}, el('span', { title: m.url }, name), el('span', { className: 'mute' }, size(m.size) || (m.type === 'HLS' ? 'flux vidéo' : ''))), b));
    }
  }
}
$('#enabled').onchange = e => ask({ type: 'enable', value: e.target.checked });
refresh();
