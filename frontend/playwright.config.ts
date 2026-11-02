import { defineConfig, devices } from '@playwright/test'

/** Runs against `docker compose up` (http://localhost:8080) with a Check Share Code sandbox key. */
export default defineConfig({
  testDir: './e2e',
  timeout: 240_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'pixel-7',
      use: {
        ...devices['Pixel 7'],
        permissions: ['camera'],
        // A fake front camera, so the live face scan works headless.
        launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
      },
    },
  ],
})
