import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:9527',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'cd ../.. && uv run python run_server.py --dev --host 0.0.0.0 --port 9527',
    url: 'http://localhost:9527',
    reuseExistingServer: true,
    timeout: 30000,
    cwd: '../..',
  },
})
