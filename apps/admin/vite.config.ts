import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { defineConfig } from 'vite';
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@redmoor/assistant-widget', replacement: resolve(import.meta.dirname, '../assistant/src/index.ts') },
    ],
  },
});
