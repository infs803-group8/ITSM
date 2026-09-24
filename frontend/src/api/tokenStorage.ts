// Keep the bearer token in memory. Reloading the page requires sign-in again.
// Never persist tokens in localStorage or put them into URLs/logs.
let accessToken: string | null = null;

export const tokenStorage = {
  get: () => accessToken,
  set(token: string) {
    accessToken = token.trim() || null;
  },
  clear() {
    accessToken = null;
  },
};
