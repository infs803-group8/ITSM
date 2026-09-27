import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  workers: 2,
  use: {
    baseURL: "http://127.0.0.1:5183",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5183 --strictPort --force",
    url: "http://127.0.0.1:5183",
    reuseExistingServer: false,
    env: { VITE_USE_MOCKS: "true", VITE_API_BASE_URL: "http://127.0.0.1:5183/api/v1" },
  },
});
