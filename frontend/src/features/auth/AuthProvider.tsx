import { createContext, useCallback, useContext, useEffect, useRef, useState, type PropsWithChildren } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { login, logout } from "../../api/auth";
import { api10GetMyProfile } from "../../api/generated/sdk.gen";
import { onUnauthorized } from "../../api/httpClient";
import { tokenStorage } from "../../api/tokenStorage";
import type { LoginRequest, UserProfile } from "../../api/types";

type SessionStatus = "anonymous" | "restoring" | "authenticated" | "restore-error";
type AuthContextValue = {
  user: UserProfile | null;
  status: SessionStatus;
  sessionVersion: number;
  sessionExpired: boolean;
  restoreError: unknown;
  signIn: (credentials: LoginRequest, signal?: AbortSignal) => Promise<void>;
  signOut: () => void;
  retrySession: () => void;
  acceptProfile: (profile: UserProfile, expectedVersion: number) => boolean;
};
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [status, setStatus] = useState<SessionStatus>(() => tokenStorage.get() ? "restoring" : "anonymous");
  const [sessionExpired, setSessionExpired] = useState(false);
  const [restoreError, setRestoreError] = useState<unknown>(null);
  const [sessionVersion, setSessionVersion] = useState(0);
  const version = useRef(0);
  const userRef = useRef<UserProfile | null>(null);
  const pending = useRef<AbortController | null>(null);

  const resetSession = useCallback((expired = false) => {
    version.current += 1;
    pending.current?.abort();
    logout();
    queryClient.clear();
    userRef.current = null;
    setUser(null);
    setStatus("anonymous");
    setSessionVersion(version.current);
    setSessionExpired(expired);
    setRestoreError(null);
  }, [queryClient]);

  const signIn = useCallback(async (credentials: LoginRequest, signal?: AbortSignal) => {
    resetSession();
    const expectedVersion = version.current;
    const controller = new AbortController();
    pending.current = controller;
    const cancel = () => controller.abort();
    signal?.addEventListener("abort", cancel, { once: true });
    if (signal?.aborted) controller.abort();
    try {
      const session = await login(credentials, controller.signal);
      if (controller.signal.aborted || expectedVersion !== version.current) return;
      userRef.current = session.user;
      setUser(session.user);
      setStatus("authenticated");
    } finally {
      signal?.removeEventListener("abort", cancel);
    }
  }, [resetSession]);

  const retrySession = useCallback(() => {
    if (!tokenStorage.get()) { resetSession(); return; }
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    const expectedVersion = version.current;
    setStatus("restoring");
    setRestoreError(null);
    void api10GetMyProfile({ signal: controller.signal }).then((response) => {
      if (controller.signal.aborted || expectedVersion !== version.current) return;
      userRef.current = response.data.data;
      setUser(response.data.data);
      setStatus("authenticated");
    }).catch((error: unknown) => {
      if (controller.signal.aborted || expectedVersion !== version.current) return;
      setRestoreError(error);
      setStatus("restore-error");
    });
  }, [resetSession]);

  useEffect(() => {
    const unsubscribe = onUnauthorized(() => resetSession(true));
    if (tokenStorage.get()) retrySession();
    return () => { unsubscribe(); pending.current?.abort(); };
  }, [resetSession, retrySession]);

  const acceptProfile = useCallback((profile: UserProfile, expectedVersion: number) => {
    // A response from a previous session must never repopulate a signed-out account.
    if (expectedVersion !== version.current || !tokenStorage.get() || profile.user_id !== userRef.current?.user_id) return false;
    userRef.current = profile;
    setUser(profile);
    return true;
  }, []);
  const signOut = useCallback(() => resetSession(), [resetSession]);

  return <AuthContext.Provider value={{ user, status, sessionVersion, sessionExpired, restoreError,
    signIn, signOut, retrySession, acceptProfile }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
