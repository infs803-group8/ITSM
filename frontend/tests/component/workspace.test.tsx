import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ConfigProvider } from "antd";
import { http, HttpResponse, getResponse } from "msw";
import { setupServer } from "msw/node";
import { AppRouter } from "../../src/app/router";
import { AuthProvider } from "../../src/features/auth/AuthProvider";
import { handlers, mockApiUrl, mockError } from "../../src/mocks/handlers";
import { mockCredentials, mockState, resetMockState } from "../../src/mocks/state";
import { login } from "../../src/api/auth";
import { tokenStorage } from "../../src/api/tokenStorage";
import { helpdeskTheme } from "../../src/styles/theme";
import * as transfer from "../../src/api/attachmentTransfer";
import { useWrite, useDownload, useWorkspaceKey } from "../../src/features/workspace/shared";
import fixtures from "../../src/mocks/fixtures.generated.json";
import type { AttachmentConfig } from "../../src/api/types";

const server = setupServer(...handlers); let client: QueryClient;
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => { resetMockState(); tokenStorage.clear(); });
afterEach(() => { cleanup(); client?.clear(); server.resetHandlers(); vi.restoreAllMocks(); tokenStorage.clear(); });
afterAll(() => server.close());
async function mount(path = "/tickets/5001", email = "user@example.com", content = <AppRouter />) {
  await login({ ...mockCredentials, email });
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<ConfigProvider theme={helpdeskTheme}><QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><AuthProvider>{content}</AuthProvider></MemoryRouter></QueryClientProvider></ConfigProvider>);
}
const click = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const fill = (name: string, value: string) => fireEvent.change(screen.getByLabelText(name, { exact: true }), { target: { value } });
function deferred() { let resolve!: () => void; const promise = new Promise<void>((done) => { resolve = done; }); return { promise, resolve }; }

describe("D03 page boundaries and recovery", () => {
  it("shows loading, 503 with request ID, retry and the actual empty list", async () => {
    const delayed = deferred(); let fail = true;
    server.use(http.get(mockApiUrl("/tickets"), async ({ request }) => { await delayed.promise; return fail ? mockError(request, 503, "SERVICE_UNAVAILABLE", "Queue temporarily unavailable.") : HttpResponse.json({ data: [], meta: { page: 1, page_size: 20, total: 0, total_pages: 0 } }); }));
    await mount("/tickets"); await screen.findByRole("heading", { name: "Tickets" });
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    delayed.resolve(); expect(await screen.findByRole("alert")).toHaveTextContent("Queue temporarily unavailable.");
    expect(screen.getByRole("alert")).toHaveTextContent("Request ID:"); fail = false; click("Try again");
    expect(await screen.findByText("No tickets match these filters.")).toBeVisible();
  });
  it("hides engineer actions and preserves null fields without crashing", async () => {
    const ticket = mockState.tickets.get(5001)!; ticket.assignee = null; ticket.sla = null; ticket.description = null;
    await mount(); await screen.findByRole("heading", { name: ticket.title });
    expect(screen.queryByRole("button", { name: "Submit resolution" })).not.toBeInTheDocument();
    expect(screen.getByText("No description available.")).toBeVisible();
  });
  it("does not query ordinary comments for vendor", async () => {
    const comments = vi.fn(); server.use(http.get(mockApiUrl("/tickets/:id/comments"), () => { comments(); return HttpResponse.error(); }));
    await mount("/tickets/6001", "vendor@example.com"); await screen.findByRole("heading", { name: "Router firmware investigation" });
    expect(screen.queryByText("Other requester")).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Comments" })).not.toBeInTheDocument();
    expect(comments).not.toHaveBeenCalled();
  });
  it("routes expired authentication to login without retaining ticket data", async () => {
    server.use(http.get(mockApiUrl("/tickets/:id"), ({ request }) => mockError(request, 401, "INVALID_ACCESS_TOKEN", "Session expired.")));
    await mount(); expect(await screen.findByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
    expect(tokenStorage.get()).toBeNull(); expect(client.getQueryCache().findAll({ queryKey: ["workspace"] })).toHaveLength(0);
  });
  it.each([403, 404])("leaves detail and clears detail caches on %i", async (status) => {
    server.use(http.get(mockApiUrl("/tickets/:id"), ({ request }) => mockError(request, status, status === 403 ? "DATA_SCOPE_DENIED" : "RESOURCE_NOT_FOUND", "Unavailable.")));
    await mount(); expect(await screen.findByRole("heading", { name: "Tickets" })).toBeVisible();
    expect(screen.getByText("This ticket is no longer available to your account.")).toBeVisible();
    await waitFor(() => expect(client.getQueryCache().getAll().some((q) => q.queryKey.includes("ticket"))).toBe(false));
  });
  it("409 workflow conflict stops repeat writes and reloads current actions", async () => {
    let calls = 0;
    server.use(http.post(mockApiUrl("/tickets/:id/resolve"), ({ request }) => { calls++; mockState.tickets.get(5001)!.status = "CLOSED"; return mockError(request, 409, "INVALID_STATUS_TRANSITION", "Another actor closed this ticket."); }));
    await mount("/tickets/5001", "tier1@example.com"); await screen.findByRole("button", { name: "Submit resolution" }); click("Submit resolution");
    fill("Resolution summary", "Proposed fix"); click("Confirm Resolve");
    expect(await screen.findByRole("alert")).toHaveTextContent("Another actor closed this ticket."); expect(screen.getByRole("button", { name: "Confirm Resolve" })).toBeDisabled();
    click("Reload ticket"); await waitFor(() => expect(screen.queryByRole("button", { name: "Submit resolution" })).not.toBeInTheDocument()); expect(calls).toBe(1);
  });
  it("validation errors preserve comment drafts for correction", async () => {
    server.use(http.post(mockApiUrl("/tickets/:id/comments"), ({ request }) => mockError(request, 422, "VALIDATION_ERROR", "Check the comment.")));
    await mount(); await screen.findByLabelText("Comment", { exact: true }); fill("Comment", "Keep this draft"); click("Add comment");
    expect(await screen.findByRole("alert")).toHaveTextContent("Check the comment."); expect(screen.getByLabelText("Comment", { exact: true })).toHaveValue("Keep this draft");
  });
  it("confirmation retry does not request another presign or upload bytes again", async () => {
    let presigns = 0; let completes = 0; const uploadId = crypto.randomUUID();
    server.use(http.post(mockApiUrl("/tickets/:id/attachments/presign"), async ({ request }) => { presigns++; expect(await request.json()).toMatchObject({ file_name: "debug.log", content_type: "text/plain" }); return HttpResponse.json({ data: { upload_id: uploadId, upload_url: "https://storage.example.test/object", method: "PUT", signed_headers: { "Content-Type": "text/plain" }, expires_at: "2099-01-01T00:00:00Z", max_size_bytes: 10485760 } }, { status: 201 }); }),
      http.post(mockApiUrl("/tickets/:id/attachments/complete"), async ({ request }) => { completes++; expect(await request.json()).toEqual({ upload_id: uploadId });
        return completes === 1 ? mockError(request, 503, "STORAGE_UNAVAILABLE", "Retry confirmation.") : HttpResponse.json({ data: { attachment_id: crypto.randomUUID(), ticket_id: 5001, file_name: "debug.log", size_bytes: 3, content_type: "text/plain", visibility: "USER_VISIBLE", created_at: "2026-09-28T00:00:00Z" } }); }));
    const put = vi.spyOn(transfer, "putAttachment").mockResolvedValue();
    await mount(); await screen.findByRole("button", { name: "Attachments" }); click("Attachments");
    const input = await screen.findByLabelText("Attachment file");
    fireEvent.change(input, { target: { files: [new File(["log"], "debug.log")] } });
    await waitFor(() => expect(screen.getByRole("button", { name: "Upload attachment" })).toBeEnabled()); click("Upload attachment");
    await screen.findByRole("alert"); click("Retry confirmation"); await screen.findByText("Attachment confirmed and added to this ticket.");
    expect(presigns).toBe(1); expect(put).toHaveBeenCalledOnce(); expect(completes).toBe(2);
  });
  it("write lock covers pending cancellation; unmount aborts before HTTP", async () => {
    const pending = deferred(); const work = vi.fn().mockResolvedValue("done"); const accepted = vi.fn();
    function Probe() { const write = useWrite(); return <button onClick={() => void write.run(work, accepted)}>Write</button>; }
    const view = await mount("/profile", "user@example.com", <Probe />); await screen.findByRole("button", { name: "Write" });
    vi.spyOn(client, "cancelQueries").mockImplementation(async () => { await pending.promise; });
    click("Write"); click("Write"); expect(work).not.toHaveBeenCalled(); view.unmount();
    await act(async () => { pending.resolve(); await pending.promise; }); expect(work).not.toHaveBeenCalled(); expect(accepted).not.toHaveBeenCalled();
  });
  it("enforces file size, extension and MIME matching before presign", () => {
    const config = { max_size_bytes: 10485760, upload_url_ttl_seconds: 900, download_url_ttl_seconds: 300, allowed_types: [{ extension: "png", content_type: "image/png" }] } as const;
    const mutable = { ...config, allowed_types: [...config.allowed_types] };
    expect(transfer.validateAttachment(new File([], "empty.png", { type: "image/png" }), mutable)).toContain("non-empty");
    expect(transfer.validateAttachment(new File(["x"], "wrong.exe", { type: "image/png" }), mutable)).toContain("must match");
    expect(transfer.validateAttachment(new File(["x"], "valid.png", { type: "image/png" }), mutable)).toBeNull();
    expect(() => transfer.safeTransferUrl("javascript:alert(1)")).toThrow();
  });
  it("locks duplicate writes and cancels reads again before accepting success", async () => {
    const pending = deferred(); const work = vi.fn(async () => { await pending.promise; return "saved"; }); const accepted = vi.fn();
    function Probe() { const write = useWrite(); return <button onClick={() => void write.run(work, accepted)}>Write</button>; }
    await mount("/profile", "user@example.com", <Probe />); const cancel = vi.spyOn(client, "cancelQueries");
    click("Write"); click("Write"); await waitFor(() => expect(work).toHaveBeenCalledOnce());
    expect(accepted).not.toHaveBeenCalled();
    await act(async () => { pending.resolve(); await pending.promise; });
    await waitFor(() => expect(accepted).toHaveBeenCalledExactlyOnceWith("saved")); expect(cancel).toHaveBeenCalledTimes(2);
  });
  it("does not accept a completed write after its page unmounts", async () => {
    const pending = deferred(); const work = vi.fn(async () => { await pending.promise; return "old session"; }); const accepted = vi.fn();
    function Probe() { const write = useWrite(); return <button onClick={() => void write.run(work, accepted)}>Write</button>; }
    const view = await mount("/profile", "user@example.com", <Probe />); click("Write"); await waitFor(() => expect(work).toHaveBeenCalledOnce());
    view.unmount(); await act(async () => { pending.resolve(); await pending.promise; }); expect(accepted).not.toHaveBeenCalled();
  });
});

describe("PR51 review regressions", () => {
  it("uses only reference-data MIME fallback and retains size/name/type guards", () => {
    const config: AttachmentConfig = { max_size_bytes: 10485760, upload_url_ttl_seconds: 900, download_url_ttl_seconds: 300,
      allowed_types: [{ extension: ".log", content_type: "text/plain" }, { extension: "png", content_type: "image/png" }] };
    expect(transfer.resolveAttachment(new File(["log"], "DEBUG.LOG"), config)).toEqual({ error: null, contentType: "text/plain" });
    expect(transfer.resolveAttachment(new File(["x"], "test.png", { type: "image/png" }), config)).toEqual({ error: null, contentType: "image/png" });
    expect(transfer.validateAttachment(new File(["x"], "wrong.log", { type: "image/png" }), config)).toContain("must match");
    expect(transfer.validateAttachment(new File(["x"], "wrong.exe"), config)).toContain("must match");
    expect(transfer.validateAttachment(new File([], "empty.log"), config)).toContain("non-empty");
    expect(transfer.validateAttachment(new File([new Uint8Array(config.max_size_bytes + 1)], "big.log"), config)).toContain("non-empty");
    expect(transfer.validateAttachment(new File(["x"], `${"x".repeat(252)}.log`), config)).toContain("255");
  });

  it.each([200, 503])("download %i does not cancel delayed reference data or duplicate requests", async (status) => {
    const reference = deferred(); const download = deferred(); let referenceSignal: AbortSignal | undefined; let calls = 0;
    const attachmentId = crypto.randomUUID();
    mockState.attachments.set(5001, [{ attachment_id: attachmentId, ticket_id: 5001, file_name: "debug.log", content_type: "text/plain", size_bytes: 3, visibility: "USER_VISIBLE", created_at: "2026-09-28T00:00:00Z" }]);
    server.use(http.get(mockApiUrl("/reference-data"), async ({ request }) => {
      referenceSignal = request.signal; await reference.promise;
      return HttpResponse.json(fixtures.operations.api12ReferenceData.body);
    }), http.get(mockApiUrl("/tickets/:id/attachments/:attachment_id/download"), async ({ request }) => {
      calls++; await download.promise;
      return status === 200 ? HttpResponse.json({ data: { attachment_id: attachmentId, file_name: "debug.log", content_type: "text/plain", download_url: "https://storage.example.test/debug.log", expires_at: "2099-01-01T00:00:00Z" } }) : mockError(request, 503, "STORAGE_UNAVAILABLE", "Download temporarily unavailable.");
    }));
    const anchor = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    try {
      await mount(); await screen.findByRole("button", { name: "Attachments" }); click("Attachments");
      await screen.findByRole("button", { name: "Download debug.log" });
      await waitFor(() => expect(referenceSignal).toBeDefined());
      expect(screen.getByLabelText("Attachment file")).toBeDisabled();
      const cancel = vi.spyOn(client, "cancelQueries"); const invalidate = vi.spyOn(client, "invalidateQueries");
      click("Download debug.log"); click("Download debug.log");
      await waitFor(() => expect(calls).toBe(1));
      download.resolve();
      if (status === 200) await waitFor(() => expect(anchor).toHaveBeenCalledOnce());
      else expect(await screen.findByRole("alert")).toHaveTextContent("Download temporarily unavailable.");
      expect(cancel).not.toHaveBeenCalled(); expect(invalidate).not.toHaveBeenCalled();
      expect(referenceSignal?.aborted).toBe(false);
      reference.resolve(); await waitFor(() => expect(screen.getByLabelText("Attachment file")).toBeEnabled());
      expect(client.getQueryCache().getAll().find((query) => query.queryKey[3] === "reference")?.state).toMatchObject({ status: "success", fetchStatus: "idle" });
      expect(calls).toBe(1);
    } finally { reference.resolve(); download.resolve(); }
  });

  it("aborts a download on unmount and never accepts its late result", async () => {
    const pending = deferred(); const accepted = vi.fn(); let signal: AbortSignal | undefined;
    const work = vi.fn(async (value: AbortSignal) => { signal = value; await pending.promise; return "url"; });
    function Probe() { const download = useDownload(); return <button onClick={() => void download.run(work, accepted)}>Download</button>; }
    const view = await mount("/profile", "user@example.com", <Probe />);
    click("Download"); click("Download"); expect(work).toHaveBeenCalledOnce();
    view.unmount(); expect(signal?.aborted).toBe(true);
    await act(async () => { pending.resolve(); await pending.promise; }); expect(accepted).not.toHaveBeenCalled();
  });

  it.each([false, true])("write failure=%s resumes affected reads without cancelling reference, vendors or another ticket", async (fail) => {
    const pending = deferred(); const writing = deferred(); const calls = new Map<string, number>(); const aborted = new Map<string, number>();
    const accepted = vi.fn();
    function Read({ part, id }: { part: string; id?: number }) {
      const key = useWorkspaceKey();
      const name = `${part}-${id ?? "all"}`;
      const query = useQuery({ queryKey: [...key, part, ...(id ? [id] : [])], enabled: key[1] !== undefined, queryFn: async ({ signal }) => {
        calls.set(name, (calls.get(name) ?? 0) + 1);
        signal.addEventListener("abort", () => aborted.set(name, (aborted.get(name) ?? 0) + 1), { once: true });
        await pending.promise; signal.throwIfAborted(); return "ready";
      } });
      return <span data-testid={name}>{query.status}/{query.fetchStatus}</span>;
    }
    function Probe() {
      const write = useWrite(5001);
      return <><Read part="reference" /><Read part="vendors" /><Read part="ticket" id={5002} /><Read part="ticket" id={5001} />
        <button onClick={() => void write.run(async () => { await writing.promise; if (fail) throw new Error("Save failed"); return "saved"; }, accepted)}>Write</button>
        {write.error != null && <p>Save failed</p>}</>;
    }
    try {
      await mount("/profile", "user@example.com", <Probe />); await waitFor(() => expect(calls.size).toBe(4));
      click("Write"); await waitFor(() => expect(aborted.get("ticket-5001")).toBe(1));
      writing.resolve();
      await waitFor(() => expect(calls.get("ticket-5001")).toBe(2));
      expect([...aborted.keys()]).toEqual(["ticket-5001"]);
      pending.resolve();
      for (const name of calls.keys()) await waitFor(() => expect(screen.getByTestId(name)).toHaveTextContent("success/idle"));
      if (fail) { expect(accepted).not.toHaveBeenCalled(); expect(screen.getByText("Save failed")).toBeVisible(); }
      else expect(accepted).toHaveBeenCalledExactlyOnceWith("saved");
    } finally { pending.resolve(); writing.resolve(); }
  });

  it.each([
    { action: "CLOSE", length: 1000, max: 1000 },
    { action: "CLOSE", length: 0, max: 1000 },
    { action: "REOPEN", length: 4000, max: 4000 },
  ])("accepts $action reason length $length using the canonical limit", async ({ action, length, max }) => {
    const ticket = mockState.tickets.get(5001)!;
    ticket.status = "RESOLVED"; ticket.resolution = { summary: "Fixed", type: "USER_CONFIRMED", resolved_at: new Date().toISOString(), auto_close_at: "2099-01-01T00:00:00Z" }; let body: unknown;
    server.use(http.post(mockApiUrl(`/tickets/:id/${action.toLowerCase()}`), async ({ request }) => {
      body = await request.clone().json(); return await getResponse(handlers, request) ?? HttpResponse.error();
    }));
    await mount(); await screen.findByRole("button", { name: action === "CLOSE" ? "Close ticket" : "Reopen ticket" });
    click(action === "CLOSE" ? "Close ticket" : "Reopen ticket");
    const input = screen.getByLabelText(action === "CLOSE" ? "Reason (optional)" : "Reason");
    expect(input).toHaveAttribute("maxlength", String(max)); fireEvent.change(input, { target: { value: "x".repeat(length) } });
    if (action === "CLOSE") fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(body).toEqual(action === "CLOSE" ? { acknowledge: true, ...(length ? { reason: "x".repeat(length) } : {}) } : { reason: "x".repeat(length) }));
    await waitFor(() => expect(ticket.status).toBe(action === "CLOSE" ? "CLOSED" : "REOPENED"));
  });

  it.each([
    { action: "CLOSE", value: "x".repeat(1001), error: "1000 characters" },
    { action: "REOPEN", value: "x".repeat(4001), error: "4000 characters" },
    { action: "REOPEN", value: "   ", error: "not only spaces" },
  ])("blocks invalid $action before HTTP ($error)", async ({ action, value, error }) => {
    mockState.tickets.get(5001)!.status = "RESOLVED"; const submitted = vi.fn();
    server.use(http.post(mockApiUrl(`/tickets/:id/${action.toLowerCase()}`), () => { submitted(); return HttpResponse.json({ data: {} }); }));
    await mount(); await screen.findByRole("button", { name: action === "CLOSE" ? "Close ticket" : "Reopen ticket" });
    click(action === "CLOSE" ? "Close ticket" : "Reopen ticket");
    const input = screen.getByLabelText(action === "CLOSE" ? "Reason (optional)" : "Reason");
    fireEvent.change(input, { target: { value } }); if (action === "CLOSE") fireEvent.click(screen.getByRole("checkbox"));
    // Bypass native maxlength deliberately: the submit handler must guard too.
    fireEvent.submit(input.closest("form")!);
    expect(await screen.findByRole("alert")).toHaveTextContent(error); expect(submitted).not.toHaveBeenCalled();
  });
});

describe("D04 vendor history", () => {
  it("loads API-33 only for an authorised role and recovers from a read failure", async () => {
    let fail = true; let calls = 0;
    server.use(http.get(mockApiUrl("/tickets/:id/vendor-requests"), ({ request }) => {
      calls++;
      return fail ? mockError(request, 503, "SERVICE_UNAVAILABLE", "History temporarily unavailable.") : HttpResponse.json({ data: [] });
    }));
    await mount("/tickets/6001", "tier2@example.com");
    await screen.findByRole("heading", { name: "Router firmware investigation" });
    click("Vendor history");
    expect(await screen.findByRole("alert")).toHaveTextContent("History temporarily unavailable.");
    expect(screen.getByRole("alert")).toHaveTextContent("Request ID:");
    fail = false; click("Try again");
    expect(await screen.findByText("No vendor requests have been recorded for this ticket.")).toBeVisible();
    expect(calls).toBe(2);
  });

  it.each([
    { email: "user@example.com", path: "/tickets/5001" },
    { email: "tier1@example.com", path: "/tickets/5001" },
  ])("does not expose or call API-33 for $email", async ({ email, path }) => {
    const calls = vi.fn(); server.use(http.get(mockApiUrl("/tickets/:id/vendor-requests"), () => { calls(); return HttpResponse.error(); }));
    await mount(path, email); await screen.findByRole("heading", { name: "Cannot connect to office Wi-Fi" });
    expect(screen.queryByRole("button", { name: "Vendor history" })).not.toBeInTheDocument(); expect(calls).not.toHaveBeenCalled();
  });

  it("refreshes the active API-33 history with the ticket subtree", async () => {
    let calls = 0; let message = "Initial persisted reply";
    server.use(http.get(mockApiUrl("/tickets/:id/vendor-requests"), () => {
      calls++;
      return HttpResponse.json({ data: [{ vendor_request_id: 1, vendor_org: { vendor_org_id: 1, name: "Example Support Ltd", is_active: true }, status: "RESPONDED",
        vendor_message: "Please investigate.", created_at: "2026-09-01T00:00:00Z", responded_at: "2026-09-01T01:00:00Z",
        response: { vendor_response_id: 2, vendor_request_id: 1, message, created_at: "2026-09-01T01:00:00Z" } }] });
    }));
    await mount("/tickets/6001", "tier2@example.com"); await screen.findByRole("heading", { name: "Router firmware investigation" });
    click("Vendor history"); expect(await screen.findByText("Initial persisted reply")).toBeVisible();
    message = "Reply loaded by manual refresh"; click("Refresh ticket");
    expect(await screen.findByText("Reply loaded by manual refresh")).toBeVisible(); expect(calls).toBe(2);
  });
});
