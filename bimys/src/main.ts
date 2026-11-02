import './styles.css';
import { App } from './ui/app';

const app = new App();
app.start(document.getElementById('app')!).catch((e) => {
  console.error(e);
  document.getElementById('app')!.innerHTML = `<div style="padding:24px;font-family:sans-serif"><h2>Bimys n'a pas pu démarrer</h2><pre>${String(e?.message ?? e)}</pre></div>`;
});
