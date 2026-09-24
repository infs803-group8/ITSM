import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The SDK may first be imported by a lazy page (or the browser smoke check).
  // Prebundle Axios so that first use does not trigger a dev-server page reload.
  optimizeDeps: { include: ["axios"] },
  server: { port: 5173 },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}", "tests/api/**/*.test.ts", "tests/component/**/*.test.{ts,tsx}"],
  },
});
