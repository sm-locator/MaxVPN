import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e', testMatch: '**/*.live.ts', workers: 1,
  timeout: 120_000, expect: { timeout: 20_000 },
  use: { baseURL: 'http://127.0.0.1:4179', trace: 'retain-on-failure', actionTimeout: 15_000 },
})
