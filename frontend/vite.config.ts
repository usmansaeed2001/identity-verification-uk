/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Lets a phone reach the dev server through a cloudflared tunnel (the camera needs HTTPS).
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/api': backend,
      '/admin': backend,
      '/static': backend,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
