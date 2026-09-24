import { defineConfig } from "@playwright/test";

// A separate port/config keeps this check independent of your normal dev server.
export default defineConfig({
  testDir: "./tests/api-browser",
  fullyParallel: true,
  use: { baseURL: "http://127.0.0.1:5181", trace: "on-first-retry" },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 5181 --strictPort --force",
    url: "http://127.0.0.1:5181",
    reuseExistingServer: false,
    env: { VITE_USE_MOCKS: "true", VITE_API_BASE_URL: "http://127.0.0.1:5181/api/v1" },
  },
});
