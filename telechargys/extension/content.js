// Telechargys : bouton « Télécharger cette vidéo » sur les vidéos des pages + Alt + clic.
(() => {
  if (window.__telechargys) return;
  window.__telechargys = true;
  const api = typeof browser !== 'undefined' ? browser : chrome;
  const msg = m => new Promise(r => { try { api.runtime.sendMessage(m, x => { void api.runtime.lastError; r(x); }); } catch (e) { r(null); } });

  // Alt maintenu pendant le clic : le téléchargement reste dans le navigateur
  addEventListener('click', e => { if (e.altKey) msg({ type: 'altClick' }); }, true);

  msg({ type: 'videoButtonEnabled' }).then(r => { if (r && r.enabled) init(); });

  function init() {
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;z-index:2147483647;top:0;left:0;display:none;';
    const root = host.attachShadow({ mode: 'closed' });
    root.innerHTML = `<style>
      button{all:initial;display:flex;align-items:center;gap:7px;font:600 13px system-ui,"Segoe UI",sans-serif;color:#fff;background:#0e9f6e;
        padding:7px 12px 7px 10px;border-radius:18px;cursor:pointer;box-shadow:0 3px 14px rgba(0,0,0,.35);opacity:.93;transition:opacity .15s,transform .15s}
      button:hover{opacity:1;transform:translateY(-1px)}
      button.err{background:#d64545} button.ok{background:#0b7a6e}
      svg{width:16px;height:16px;stroke:#fff;fill:none;stroke-width:2.6;stroke-linecap:round;stroke-linejoin:round}
      .x{margin-left:4px;opacity:.75;font-weight:400}
    </style><button title="Télécharger cette vidéo avec Telechargys"><svg viewBox="0 0 24 24"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></svg><span>Télécharger cette vidéo</span><span class="x" title="Masquer">✕</span></button>`;
    const btn = root.querySelector('button'), label = root.querySelector('span');
    (document.body || document.documentElement).appendChild(host);
    let cur = null, hideT = 0, hidden = new WeakSet();

    function place(v) {
      const r = v.getBoundingClientRect();
      host.style.display = 'block';
      const w = btn.offsetWidth || 210;
      host.style.left = Math.max(4, Math.min(innerWidth - w - 4, r.right - w - 10)) + 'px';
      host.style.top = Math.max(4, r.top + 10) + 'px';
    }
    function videoAt(x, y) {
      for (const v of document.querySelectorAll('video')) {
        const r = v.getBoundingClientRect();
        if (r.width >= 200 && r.height >= 120 && x >= r.left && x <= r.right && y >= r.top && y <= r.bottom && !hidden.has(v)) return v;
      }
      return null;
    }
    let raf = 0;
    addEventListener('mousemove', e => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        if (e.composedPath && e.composedPath().includes(host)) { clearTimeout(hideT); return; }
        const v = videoAt(e.clientX, e.clientY);
        if (v) { clearTimeout(hideT); if (cur !== v) { cur = v; reset(); } place(v); }
        else if (cur) { clearTimeout(hideT); hideT = setTimeout(() => { host.style.display = 'none'; cur = null; }, 1200); }
      });
    }, { passive: true });
    addEventListener('scroll', () => { if (cur) place(cur); }, { passive: true, capture: true });
    function reset() { btn.className = ''; label.textContent = 'Télécharger cette vidéo'; }
    btn.addEventListener('click', async e => {
      e.preventDefault(); e.stopPropagation();
      if (e.target.classList.contains('x')) { if (cur) hidden.add(cur); host.style.display = 'none'; cur = null; return; }
      if (!cur) return;
      label.textContent = 'Envoi…';
      const r = await msg({ type: 'videoButton', src: cur.currentSrc || cur.src || '', title: document.title, pageUrl: location.href });
      if (r && r.ok) { btn.className = 'ok'; label.textContent = 'Envoyé à Telechargys ✓'; }
      else { btn.className = 'err'; label.textContent = (r && r.error) || 'Telechargys est-il lancé ?'; }
      setTimeout(reset, 4000);
    }, true);
  }
})();
