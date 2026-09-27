import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ConfigProvider } from "antd";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { AppRouter } from "../../src/app/router";
import { AuthProvider } from "../../src/features/auth/AuthProvider";
import { handlers, mockApiUrl, mockError } from "../../src/mocks/handlers";
import { mockCredentials, mockState, resetMockState } from "../../src/mocks/state";
import { login } from "../../src/api/auth";
import { tokenStorage } from "../../src/api/tokenStorage";
import { helpdeskTheme } from "../../src/styles/theme";
import * as transfer from "../../src/api/attachmentTransfer";
import { useWrite } from "../../src/features/workspace/shared";

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
    server.use(http.post(mockApiUrl("/tickets/:id/attachments/presign"), () => { presigns++; return HttpResponse.json({ data: { upload_id: uploadId, upload_url: "https://storage.example.test/object", method: "PUT", signed_headers: { "Content-Type": "text/plain" }, expires_at: "2099-01-01T00:00:00Z", max_size_bytes: 10485760 } }, { status: 201 }); }),
      http.post(mockApiUrl("/tickets/:id/attachments/complete"), async ({ request }) => { completes++; expect(await request.json()).toEqual({ upload_id: uploadId });
        return completes === 1 ? mockError(request, 503, "STORAGE_UNAVAILABLE", "Retry confirmation.") : HttpResponse.json({ data: { attachment_id: crypto.randomUUID(), ticket_id: 5001, file_name: "debug.log", size_bytes: 3, content_type: "text/plain", visibility: "USER_VISIBLE", created_at: "2026-09-28T00:00:00Z" } }); }));
    const put = vi.spyOn(transfer, "putAttachment").mockResolvedValue();
    await mount(); await screen.findByRole("button", { name: "Attachments" }); click("Attachments");
    const input = await screen.findByLabelText("Attachment file");
    fireEvent.change(input, { target: { files: [new File(["log"], "debug.log", { type: "text/plain" })] } });
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
