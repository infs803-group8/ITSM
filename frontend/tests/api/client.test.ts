// @vitest-environment node
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  api01Health, api06DashboardSummary, api08Register, api09Login, api10GetMyProfile,
  api11UpdateMyProfile, api12ReferenceData, api15CreateTicket, api16ListTickets,
  api17GetTicket, api22StartTicket,
} from "../../src/api/generated/sdk.gen";
import type { RegisterRequest, TicketCreateRequest } from "../../src/api/generated/types.gen";
import { login, logout } from "../../src/api/auth";
import { tokenStorage } from "../../src/api/tokenStorage";
import { onUnauthorized } from "../../src/api/httpClient";
import { handlers, mockApiUrl, mockError } from "../../src/mocks/handlers";
import { mockCredentials, mockState, resetMockState } from "../../src/mocks/state";
import { assertResponse, successExample } from "./contract";

const server = setupServer(...handlers);
const requests: Request[] = [];
const newTicket: TicketCreateRequest = { title: "VPN connection issue", description: "VPN fails after restart.", category: "NETWORK", priority: "HIGH" };
beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  server.events.on("request:start", ({ request }) => { requests.push(request); });
});
beforeEach(() => { resetMockState(); tokenStorage.clear(); requests.length = 0; });
afterEach(() => { server.resetHandlers(); vi.restoreAllMocks(); });
afterAll(() => { server.close(); tokenStorage.clear(); });

describe("generated SDK through the real Axios + MSW boundary", () => {
  it("uses the health data envelope and supplies a UUID request ID", async () => {
    const result = await api01Health();
    expect(result.status).toBe(200);
    expect(result.data.data).toMatchObject({ status: "ok", checks: { database: "ok" } });
    expect(result.headers["x-request-id"]).toMatch(/^[0-9a-f-]{36}$/);
    expect(result.headers["x-request-id"]).toBe(requests[0].headers.get("X-Request-ID"));
    assertResponse("api01Health", 200, result.data);
  });

  it("logs in, stores the token, and adds Bearer only to protected endpoints", async () => {
    const session = await login(mockCredentials);
    expect(session.access_token).toMatch(/^mock-only-/);
    expect(tokenStorage.get()).toBe(session.access_token);
    const me = await api10GetMyProfile();
    expect(me.data.data).toMatchObject({ user_id: 1001, role: "USER", vendor_org: null, is_available: null });
    expect(requests.at(-1)!.headers.get("Authorization")).toBe(`Bearer ${session.access_token}`);
    assertResponse("api10GetMyProfile", 200, me.data);
    await api01Health();
    expect(requests.at(-1)!.headers.get("Authorization")).toBeNull();
    await api09Login({ body: mockCredentials });
    expect(requests.at(-1)!.headers.get("Authorization")).toBeNull();
  });

  it("preserves a caller-provided correlation ID", async () => {
    const requestId = "550e8400-e29b-41d4-a716-446655440000";
    const result = await api01Health({ headers: { "X-Request-ID": requestId } });
    expect(result.headers["x-request-id"]).toBe(requestId);
  });

  it("requires authentication and clears an expired active session exactly once", async () => {
    await expect(api10GetMyProfile()).rejects.toMatchObject({ status: 401, code: "INVALID_ACCESS_TOKEN" });
    await login(mockCredentials);
    mockState.tokens.get(tokenStorage.get()!)!.expiresAt = 0;
    const listener = vi.fn();
    const unsubscribe = onUnauthorized(listener);
    try {
      await expect(api10GetMyProfile()).rejects.toMatchObject({ status: 401, requestId: expect.any(String) });
      expect(tokenStorage.get()).toBeNull();
      expect(listener).toHaveBeenCalledOnce();
      await expect(api10GetMyProfile()).rejects.toMatchObject({ status: 401 });
      expect(listener).toHaveBeenCalledOnce();
    } finally { unsubscribe(); }
  });

  it("does not invalidate an existing session when a public login fails", async () => {
    await login(mockCredentials);
    const token = tokenStorage.get();
    await expect(login({ ...mockCredentials, password: "wrong" })).rejects.toMatchObject({ status: 401, code: "INVALID_CREDENTIALS" });
    expect(tokenStorage.get()).toBe(token);
  });

  it("does not let an old request's 401 clear a newer token", async () => {
    await login(mockCredentials);
    server.use(http.get(mockApiUrl("/users/me"), ({ request }) => {
      tokenStorage.set("newer-session");
      return mockError(request, 401, "INVALID_ACCESS_TOKEN", "Old session expired.");
    }));
    await expect(api10GetMyProfile()).rejects.toMatchObject({ status: 401 });
    expect(tokenStorage.get()).toBe("newer-session");
  });

  it("registers with display_name and rejects duplicate emails and additional fields", async () => {
    const body = { display_name: "Second User", email: "second@example.com", password: "MockPass123!" };
    const result = await api08Register({ body });
    expect(result.status).toBe(201);
    expect(result.data.data).toMatchObject({ display_name: "Second User", role: "USER" });
    assertResponse("api08Register", 201, result.data);
    await expect(api08Register({ body })).rejects.toMatchObject({ status: 409, code: "EMAIL_ALREADY_REGISTERED" });
    // Deliberately bypass TypeScript to exercise network-level request validation.
    await expect(api08Register({ body: { ...body, name: "legacy name", role: "SERVICE_DESK_MANAGER" } as RegisterRequest }))
      .rejects.toMatchObject({ status: 422, code: "VALIDATION_ERROR" });
  });

  it("updates the USER profile, persists it, and rejects engineer-only availability", async () => {
    await login(mockCredentials);
    const result = await api11UpdateMyProfile({ body: { display_name: "Updated Requester" } });
    expect(result.data.data.display_name).toBe("Updated Requester");
    assertResponse("api11UpdateMyProfile", 200, result.data);
    expect((await api10GetMyProfile()).data.data.display_name).toBe("Updated Requester");
    await expect(api11UpdateMyProfile({ body: {} })).rejects.toMatchObject({ status: 422 });
    await expect(api11UpdateMyProfile({ body: { is_available: true } })).rejects.toMatchObject({ status: 403, code: "DATA_SCOPE_DENIED" });
    expect(tokenStorage.get()).not.toBeNull();
  });

  it("returns canonical reference data", async () => {
    await login(mockCredentials);
    const result = await api12ReferenceData();
    expect(result.data.data.priorities).toEqual(["LOW", "MEDIUM", "HIGH", "URGENT"]);
    expect(result.data.data.attachment.max_size_bytes).toBe(10_485_760);
    assertResponse("api12ReferenceData", 200, result.data);
  });

  it("creates, reads, filters and paginates tickets with stable null fields", async () => {
    await login(mockCredentials);
    const created = await api15CreateTicket({ body: newTicket });
    expect(created.status).toBe(201);
    expect(created.data.data).toMatchObject({ ...newTicket, status: "UNASSIGNED", assignee: null, sla: null, vendor_request: null });
    assertResponse("api15CreateTicket", 201, created.data);
    const detail = await api17GetTicket({ path: { id: created.data.data.ticket_id } });
    expect(detail.data).toEqual(created.data);
    assertResponse("api17GetTicket", 200, detail.data);
    const list = await api16ListTickets({ query: { search: "VPN", status: "UNASSIGNED", category: "NETWORK", page: 1, page_size: 1 } });
    expect(list.data.data).toHaveLength(1);
    expect(list.data.data[0].ticket_id).toBe(created.data.data.ticket_id);
    expect(list.data.meta).toEqual({ page: 1, page_size: 1, total: 1, total_pages: 1 });
    assertResponse("api16ListTickets", 200, list.data);
    const empty = await api16ListTickets({ query: { search: "VPN", page: 2, page_size: 1 } });
    expect(empty.data.data).toEqual([]);
    expect(empty.data.meta.total).toBe(1);
  });

  it("sorts by priority and rejects invalid bodies/filters/pagination", async () => {
    await login(mockCredentials);
    await api15CreateTicket({ body: { ...newTicket, priority: "LOW" } });
    await api15CreateTicket({ body: { ...newTicket, priority: "URGENT" } });
    const list = await api16ListTickets({ query: { sort_by: "priority", sort_order: "asc" } });
    expect(list.data.data.map((ticket) => ticket.priority)).toEqual(["LOW", "HIGH", "URGENT"]);
    await expect(api15CreateTicket({ body: { ...newTicket, priority: "high" } as unknown as TicketCreateRequest })).rejects.toMatchObject({ status: 422 });
    await expect(api15CreateTicket({ body: { ...newTicket, status: "CLOSED" } as TicketCreateRequest })).rejects.toMatchObject({ status: 422 });
    await expect(api16ListTickets({ query: { page: 0 } })).rejects.toMatchObject({ status: 422 });
    await expect(api16ListTickets({ query: { page_size: 101 } })).rejects.toMatchObject({ status: 422 });
    await expect(api16ListTickets({ query: { assignee_id: 2001 } })).rejects.toMatchObject({ status: 403 });
  });

  it("isolates users' tickets and does not offer engineer actions to USER", async () => {
    await login(mockCredentials);
    const seed = await api17GetTicket({ path: { id: 5001 } });
    expect(seed.data.data.available_actions).toEqual(["COMMENT", "UPLOAD_ATTACHMENT"]);
    const credentials = { email: "isolated@example.com", password: "MockPass123!" };
    await api08Register({ body: { ...credentials, display_name: "Isolated User" } });
    await login(credentials);
    const list = await api16ListTickets();
    expect(list.data).toEqual({ data: [], meta: { page: 1, page_size: 20, total: 0, total_pages: 0 } });
    assertResponse("api16ListTickets", 200, list.data);
    await expect(api17GetTicket({ path: { id: 5001 } })).rejects.toMatchObject({ status: 404 });
    await expect(api17GetTicket({ path: { id: 99999 } })).rejects.toMatchObject({ status: 404 });
  });

  it("preserves workflow data.ticket using a test-only contract response", async () => {
    // Full engineering workflows are not implemented in the baseline USER Mock.
    server.use(http.post(mockApiUrl("/tickets/:id/start"), () => HttpResponse.json(successExample("api22StartTicket"))));
    const result = await api22StartTicket({ path: { id: 5001 } });
    expect(result.data.data.action).toBe("START");
    expect(result.data.data.ticket.status).toBe("IN_PROGRESS");
    expect(result.data.data.comment_id).toBeNull();
    assertResponse("api22StartTicket", 200, result.data);
  });

  it("fails unsupported mock operations locally instead of falling through to the backend", async () => {
    await login(mockCredentials);
    await expect(api06DashboardSummary()).rejects.toMatchObject({ kind: "network", code: "NETWORK_ERROR" });
  });

  it("logout removes the bearer token without calling a nonexistent endpoint", async () => {
    await login(mockCredentials);
    const count = requests.length;
    logout();
    expect(tokenStorage.get()).toBeNull();
    expect(requests).toHaveLength(count);
    await expect(api10GetMyProfile()).rejects.toMatchObject({ status: 401 });
  });
});
