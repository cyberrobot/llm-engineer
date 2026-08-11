import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';
import { defineConfig } from 'vitest/config';
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@redmoor/assistant-widget': resolve(import.meta.dirname, '../assistant/src/index.ts') } },
  test: { environment: 'jsdom', include: ['src/**/*.test.{ts,tsx}'], setupFiles: './src/test/setup.ts' },
});
