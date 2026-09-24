import axios from "axios";
import type { CreateClientConfig } from "./generated/client.gen";
import { apiBaseUrl } from "./config";
import { normalizeApiError, type ApiRequestError } from "./errorHandler";
import { tokenStorage } from "./tokenStorage";

export const httpClient = axios.create({
  baseURL: apiBaseUrl,
  timeout: 10_000,
});

type UnauthorizedListener = (error: ApiRequestError) => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

// The future auth UI can subscribe, clear cached user data, and navigate to login.
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => { unauthorizedListeners.delete(listener); };
}

httpClient.interceptors.request.use((config) => {
  if (!config.headers.has("X-Request-ID")) {
    config.headers.set("X-Request-ID", crypto.randomUUID());
  }
  return config;
});

httpClient.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const normalized = normalizeApiError(error);
    const token = tokenStorage.get();
    // An old request's 401 must not log out a newer session. A failed public
    // login also must not invalidate an existing authenticated session.
    if (normalized.status === 401 && token && axios.isAxiosError(error)
      && error.config?.headers.get("Authorization") === `Bearer ${token}`) {
      tokenStorage.clear();
      for (const listener of unauthorizedListeners) {
        try { listener(normalized); } catch { /* Preserve the original API error. */ }
      }
    }
    return Promise.reject(normalized);
  },
);

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  axios: httpClient,
  baseURL: apiBaseUrl,
  timeout: 10_000,
  throwOnError: true,
  // The generated SDK attaches this only to operations with BearerAuth security.
  auth: () => tokenStorage.get() ?? undefined,
});
