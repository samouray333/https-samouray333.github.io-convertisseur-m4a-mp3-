import { defineConfig, type Plugin } from 'vite';
import { copyFileSync, mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = import.meta.dirname;
const pkg = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));

/** Copie le moteur WebAssembly de web-ifc dans public/wasm (jamais chargé depuis un CDN). */
function webIfcWasm(): Plugin {
  const copy = () => {
    mkdirSync(resolve(root, 'public/wasm'), { recursive: true });
    copyFileSync(resolve(root, 'node_modules/web-ifc/web-ifc.wasm'), resolve(root, 'public/wasm/web-ifc.wasm'));
  };
  return { name: 'web-ifc-wasm', buildStart: copy, configureServer: copy };
}

export default defineConfig({
  base: './',
  plugins: [webIfcWasm()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  worker: { format: 'es' },
  build: {
    target: 'es2022',
    outDir: 'dist',
    assetsInlineLimit: 0,
    chunkSizeWarningLimit: 2500,
    rollupOptions: { output: { manualChunks: (id: string) => (/node_modules\/(three|three-mesh-bvh)\//.test(id) ? 'three' : /node_modules\/(jspdf|jspdf-autotable)\//.test(id) ? 'pdf' : undefined) } },
  },
  server: { host: true },
});
