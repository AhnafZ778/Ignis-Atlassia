import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// Output lands in the Python package so the server can serve it through a manifest allowlist.
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: fileURLToPath(new URL('../fireatlas/static/studio-assets', import.meta.url)),
    emptyOutDir: true,
    manifest: true,
    sourcemap: false,
    target: 'es2022',
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      input: { studio: fileURLToPath(new URL('./src/main.tsx', import.meta.url)), excalidraw: fileURLToPath(new URL('./src/excalidraw.tsx', import.meta.url)) },
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]'
      }
    }
  },
  test: { environment: 'jsdom', include: ['src/**/*.test.ts', 'src/**/*.test.tsx'] }
});
