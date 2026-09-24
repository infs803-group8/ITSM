import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { shouldEnableMocks } from "./api/config";
import "./styles/global.css";

async function bootstrap() {
  // Keep the DEV guard here so Vite removes the entire Mock import in production.
  if (import.meta.env.DEV && shouldEnableMocks(import.meta.env)) {
    const { worker } = await import("./mocks/browser");
    await worker.start({ onUnhandledRequest: "bypass" });
    console.info("[ITSM] Local USER Mock enabled. Data resets on reload; unsupported API calls fail locally.");
  }
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

void bootstrap().catch(() => {
  // A failed Mock setup must not silently fall back to a real backend.
  document.getElementById("root")!.textContent = "Unable to start the application. Check the local Mock setup and reload.";
});
