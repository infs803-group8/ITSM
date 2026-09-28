import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient, type Query } from "@tanstack/react-query";
import { Button } from "antd";
import { useAuth } from "../auth/AuthProvider";
import { api12ReferenceData } from "../../api/generated/sdk.gen";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";

export const label = (value: string) => value.toLowerCase().replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const date = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : "Not available";
export function useWorkspaceKey() {
  const { user, sessionVersion } = useAuth();
  return ["workspace", user?.user_id, sessionVersion] as const;
}
export function useReference() {
  const key = useWorkspaceKey();
  return useQuery({ queryKey: [...key, "reference"], queryFn: async ({ signal }) => (await api12ReferenceData({ signal })).data.data });
}
// One synchronous lock covers cancellation, HTTP writes and cache invalidation.
// Aborting on unmount prevents late responses from restoring a previous session.
function useOperation(isWrite: boolean, ticketId?: number) {
  const queryClient = useQueryClient();
  const key = useWorkspaceKey();
  const request = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => () => { request.current?.abort(); }, []);
  async function run<T>(work: (signal: AbortSignal) => Promise<T>, success: (result: T) => void) {
    if (request.current) return;
    const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(null);
    const affected = (query: Query) => key.every((part, index) => query.queryKey[index] === part) &&
      (["tickets", "dashboard", "overdue", "assignees"].includes(String(query.queryKey[3])) ||
        (ticketId !== undefined && query.queryKey[3] === "ticket" && query.queryKey[4] === ticketId));
    const cancelledReads = new Set<Query>();
    const cancelAffected = async () => {
      for (const query of queryClient.getQueryCache().findAll({ predicate: affected })) {
        if (query.state.fetchStatus === "fetching") cancelledReads.add(query);
      }
      await queryClient.cancelQueries({ predicate: affected });
    };
    let saved = false;
    try {
      if (isWrite) await cancelAffected();
      controller.signal.throwIfAborted();
      const result = await work(controller.signal);
      controller.signal.throwIfAborted();
      // A manual read may have started while the write was in flight.
      if (isWrite) await cancelAffected();
      controller.signal.throwIfAborted();
      if (isWrite) await queryClient.invalidateQueries({ predicate: affected, refetchType: "none" });
      controller.signal.throwIfAborted();
      saved = true;
      success(result);
    } catch (failure) {
      if (!controller.signal.aborted) setError(failure);
    } finally {
      if (isWrite && !controller.signal.aborted) {
        // Resume interrupted active reads even when the write fails. On success
        // refresh affected views, joining any refresh started by the callback.
        void queryClient.refetchQueries({ predicate: (query) => affected(query) && (saved || cancelledReads.has(query)), type: "active" }, { cancelRefetch: false });
      }
      if (!controller.signal.aborted) setBusy(false);
      if (request.current === controller) request.current = null;
    }
  }
  return { run, busy, error, clearError: () => setError(null) };
}
export function useWrite(ticketId?: number) { return useOperation(true, ticketId); }
// Download URL reads need the same lock/abort protection, but no cache mutation.
export function useDownload() { return useOperation(false); }
export function PageHeading({ title, note, children }: { title: string; note?: string; children?: ReactNode }) {
  return <div className="page-heading"><div><p className="eyebrow">SERVICE OPERATIONS</p><h1>{title}</h1><p>{note}</p></div>{children}</div>;
}
export function QueryNotice({ query }: { query: { isPending: boolean; error: unknown; refetch: () => unknown } }) {
  return query.isPending ? <p role="status">Loading…</p> : query.error ? <ApiErrorNotice error={query.error} onRetry={() => void query.refetch()} /> : null;
}
export function Pager({ page, total, onChange }: { page: number; total: number; onChange: (page: number) => void }) {
  return <nav className="pager" aria-label="Pagination"><Button disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</Button>
    <span>Page {page} of {Math.max(1, total)}</span><Button disabled={page >= total} onClick={() => onChange(page + 1)}>Next</Button></nav>;
}
export function Status({ value }: { value: string }) {
  return <span className={`status-chip status-${value.toLowerCase().replaceAll(" ", "_")}`}>{label(value)}</span>;
}
