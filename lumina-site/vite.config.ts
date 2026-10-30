import { defineConfig } from 'vite';

export default defineConfig({
  server: { port: 5183, strictPort: true },
  preview: { port: 4183, strictPort: true },
  build: {
    target: 'es2022',
    sourcemap: false,
    cssCodeSplit: true,
    assetsInlineLimit: 2048,
    chunkSizeWarningLimit: 700,
  },
});
