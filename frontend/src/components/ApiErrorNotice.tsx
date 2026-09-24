import { normalizeApiError } from "../api/errorHandler";

export function ApiErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const failure = normalizeApiError(error);
  if (failure.kind === "cancelled") return null;
  return (
    <div role="alert">
      <p>{failure.message}</p>
      {failure.requestId && <p>Request ID: <code>{failure.requestId}</code></p>}
      {onRetry && <button type="button" onClick={onRetry}>Try again</button>}
    </div>
  );
}
