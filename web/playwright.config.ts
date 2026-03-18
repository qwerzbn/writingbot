import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 70000,
  expect: {
    timeout: 10000,
  },
  retries: 0,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:3005',
    headless: true,
  },
  webServer: {
    command: 'NEXT_DIST_DIR=.next-playwright npm run build && NEXT_DIST_DIR=.next-playwright npm run start -- --port 3005',
    cwd: __dirname,
    url: 'http://127.0.0.1:3005/chat',
    timeout: 180000,
    reuseExistingServer: true,
  },
});
