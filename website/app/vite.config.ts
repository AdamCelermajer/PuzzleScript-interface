/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The SPA talks only to the FastAPI workbench (revamp contract §4); Vite only proxies.
// WORKBENCH_API_URL lets a test instance (e.g. :8020) stand in for the shared :8010 API.
const api = process.env.WORKBENCH_API_URL || 'http://127.0.0.1:8010'
const proxy = { '/api': { target: api, changeOrigin: true } }

// Adam opens the workbench over Tailscale: any hostname, no host restrictions.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: true, allowedHosts: true, port: 5174, strictPort: true, proxy },
  preview: { host: true, allowedHosts: true, port: 5174, strictPort: true, proxy },
  build: { outDir: 'dist', emptyOutDir: true, chunkSizeWarningLimit: 900 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
