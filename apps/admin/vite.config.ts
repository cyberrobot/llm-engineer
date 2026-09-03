import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: '@redmoor/assistant-widget', replacement: resolve(import.meta.dirname, '../../packages/assistant-widget/src/index.ts') },
    ],
  },
});
