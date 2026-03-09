import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: '/static/',
  build: {
    outDir: '../src/biblio/static',
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: 'app.js',
        chunkFileNames: 'chunk-[name].js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.css')) return 'app.css';
          return assetInfo.name || '[name][extname]';
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8010',
    },
  },
});
