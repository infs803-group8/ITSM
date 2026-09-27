import { api09Login } from "./generated/sdk.gen";
import type { LoginData, LoginRequest } from "./types";
import { tokenStorage } from "./tokenStorage";

export async function login(credentials: LoginRequest, signal?: AbortSignal): Promise<LoginData> {
  const response = await api09Login({ body: credentials, signal });
  signal?.throwIfAborted();
  tokenStorage.set(response.data.data.access_token);
  return response.data.data;
}

// There is no logout or token-refresh endpoint in the v1.1 contract.
export function logout(): void {
  tokenStorage.clear();
}
