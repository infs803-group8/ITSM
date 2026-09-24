// Same-origin /api/v1 works behind the team's reverse proxy in production.
export const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL?.trim() ||
  (import.meta.env.DEV ? "http://localhost:8000/api/v1" : "/api/v1")
).replace(/\/+$/, "");

export function shouldEnableMocks(env: { DEV: boolean; VITE_USE_MOCKS?: string }): boolean {
  return env.DEV && env.VITE_USE_MOCKS === "true";
}
