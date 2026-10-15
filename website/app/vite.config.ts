/// <reference types="vitest/config" />
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The SPA talks only to FastAPI (revamp contract §4): /api/workbench/* and /api/optimal-path/*.
// WORKBENCH_API_URL lets a test instance (e.g. :8020) stand in for the shared :8010 API.
const api = process.env.WORKBENCH_API_URL || 'http://127.0.0.1:8010'
const proxy = { '/api': { target: api, changeOrigin: true } }
// Explicit root so `vite --config website/app/vite.config.ts` works from the repo root.
const root = dirname(fileURLToPath(import.meta.url))

// Adam opens the workbench over Tailscale: any hostname, no host restrictions.
export default defineConfig({
  root,
  plugins: [react(), tailwindcss()],
  server: { host: true, allowedHosts: true, port: 5174, strictPort: true, proxy },
  preview: { host: true, allowedHosts: true, port: 5174, strictPort: true, proxy },
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 1600 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
