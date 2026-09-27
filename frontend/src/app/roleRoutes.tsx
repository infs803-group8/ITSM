import type { PropsWithChildren } from "react";
import { Navigate } from "react-router-dom";
import { Button } from "antd";
import type { Role } from "../api/types";
import { ApiErrorNotice } from "../components/ApiErrorNotice";
import { useAuth } from "../features/auth/AuthProvider";

function SessionGate() {
  const { status, restoreError, retrySession, signOut } = useAuth();
  return <main className="route-message"><h1>Checking your session</h1>
    {status === "restore-error" ? <><ApiErrorNotice error={restoreError} onRetry={retrySession} />
      <Button onClick={signOut}>Return to sign in</Button></> : <p role="status">Loading your account…</p>}
  </main>;
}

export function RoleRoute({ children, roles }: PropsWithChildren<{ roles?: readonly Role[] }>) {
  const { user, status } = useAuth();
  if (status === "restoring" || status === "restore-error") return <SessionGate />;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/forbidden" replace />;
  return children;
}

export function PublicRoute({ children }: PropsWithChildren) {
  const { user, status } = useAuth();
  if (status === "restoring" || status === "restore-error") return <SessionGate />;
  if (user) return <Navigate to="/profile" replace />;
  return children;
}
