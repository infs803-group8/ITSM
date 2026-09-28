// @vitest-environment node
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { setupServer } from "msw/node";
import { handlers } from "../../src/mocks/handlers";
import { mockCredentials, mockState, resetMockState } from "../../src/mocks/state";
import { login } from "../../src/api/auth";
import { tokenStorage } from "../../src/api/tokenStorage";
import * as api from "../../src/api/generated/sdk.gen";
import fixtures from "../../src/mocks/workspace-fixtures.generated.json";
import { assertResponse, operations, successExample } from "./contract";

const server = setupServer(...handlers);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => { resetMockState(); tokenStorage.clear(); });
afterEach(() => server.resetHandlers()); afterAll(() => { server.close(); tokenStorage.clear(); });
const signIn = (email: string) => login({ ...mockCredentials, email });
const path = { id: 5001 };
describe("D03 workspace SDK contracts and role boundaries", () => {
  it("generates every operation's examples from the canonical contract", () => {
    expect(Object.keys(fixtures.operations)).toHaveLength(32);
    for (const operation of operations) expect(fixtures.operations[operation.operationId as keyof typeof fixtures.operations].body).toEqual(successExample(operation.operationId));
  });
  it("validates list, update, comment and event response schemas", async () => {
    await signIn("user@example.com");
    const created = await api.api15CreateTicket({ body: { title: "Test issue", description: "Details", category: "NETWORK", priority: "HIGH" } });
    const updated = await api.api18UpdateTicket({ path: { id: created.data.data.ticket_id }, body: { title: "Changed" } });
    assertResponse("api18UpdateTicket", 200, updated.data);
    expect(updated.data.data.title).toBe("Changed");
    const comment = await api.api20CreateComment({ path, body: { message: "Visible message", visibility: "USER_VISIBLE" } });
    assertResponse("api20CreateComment", 201, comment.data);
    assertResponse("api19ListComments", 200, (await api.api19ListComments({ path })).data);
    assertResponse("api32ListEvents", 200, (await api.api32ListEvents({ path })).data);
    await expect(api.api20CreateComment({ path, body: { message: "Hidden", visibility: "INTERNAL_ONLY" } })).rejects.toMatchObject({ status: 403 });
  });
  it("escalates once, preserves SLA and removes Tier 1 read scope", async () => {
    await signIn("tier1@example.com"); const before = (await api.api17GetTicket({ path })).data.data;
    const response = await api.api25EscalateTicket({ path, body: { tier2_assignee_id: 2002 } });
    assertResponse("api25EscalateTicket", 200, response.data);
    expect(response.data.data.ticket.available_actions).toEqual([]); expect(response.data.data.ticket.sla).toEqual(before.sla);
    await expect(api.api17GetTicket({ path })).rejects.toMatchObject({ status: 404 });
    await signIn("tier2@example.com"); expect((await api.api17GetTicket({ path })).data.data.available_actions).toContain("START");
  });
  it("validates all user/engineer workflow envelopes and read-only closure", async () => {
    await signIn("tier1@example.com");
    assertResponse("api23RequestUserInfo", 200, (await api.api23RequestUserInfo({ path, body: { message: "Need details" } })).data);
    await signIn("user@example.com");
    await expect(api.api20CreateComment({ path, body: { message: "Not a resume", visibility: "USER_VISIBLE" } })).rejects.toMatchObject({ status: 409 });
    assertResponse("api24ResumeTicket", 200, (await api.api24ResumeTicket({ path, body: { message: "Here are details" } })).data);
    await signIn("tier1@example.com");
    assertResponse("api28ResolveTicket", 200, (await api.api28ResolveTicket({ path, body: { resolution_summary: "Fixed" } })).data);
    await signIn("user@example.com");
    assertResponse("api29ConfirmResolution", 200, (await api.api29ConfirmResolution({ path })).data);
    assertResponse("api30ReopenTicket", 200, (await api.api30ReopenTicket({ path, body: { reason: "Still fails" } })).data);
    await signIn("tier1@example.com");
    assertResponse("api22StartTicket", 200, (await api.api22StartTicket({ path })).data);
    await api.api28ResolveTicket({ path, body: { resolution_summary: "Fixed again" } });
    await signIn("user@example.com"); await api.api29ConfirmResolution({ path });
    await expect(api.api31CloseTicket({ path, body: { acknowledge: false as true } })).rejects.toMatchObject({ status: 422 });
    const closed = await api.api31CloseTicket({ path, body: { acknowledge: true } }); assertResponse("api31CloseTicket", 200, closed.data);
    expect(closed.data.data.ticket.available_actions).toEqual([]);
    await expect(api.api30ReopenTicket({ path, body: { reason: "Too late" } })).rejects.toMatchObject({ status: 409 });
  });
  it("projects vendor status and removes requester, internal data and comment access", async () => {
    await signIn("vendor@example.com"); const vendorPath = { id: 6001 };
    const detail = (await api.api17GetTicket({ path: vendorPath })).data.data;
    expect(detail).toMatchObject({ status: "PENDING_VENDOR", requester: null, description: null, sla: null, assignee: null });
    await expect(api.api19ListComments({ path: vendorPath })).rejects.toMatchObject({ status: 403 });
    const response = await api.api27VendorResponse({ path: vendorPath, body: { message: "Vendor findings" } }); assertResponse("api27VendorResponse", 200, response.data);
    expect(response.data.data.ticket.status).toBe("IN_PROGRESS"); expect(response.data.data.ticket.available_actions).toEqual([]);
    expect(response.data.data.vendor_response?.message).toBe("Vendor findings");
    const vendorEvents = (await api.api32ListEvents({ path: vendorPath })).data.data;
    expect(vendorEvents.find((entry) => entry.event_type === "VENDOR_RESPONDED")?.metadata).toEqual({});
    await signIn("tier2@example.com");
    const engineerEvents = (await api.api32ListEvents({ path: vendorPath })).data.data;
    expect(engineerEvents.find((entry) => entry.event_type === "VENDOR_RESPONDED")?.metadata).toEqual({});
    expect(JSON.stringify((await api.api17GetTicket({ path: vendorPath })).data)).not.toContain("Vendor findings");
    assertResponse("api14ListVendors", 200, (await api.api14ListVendors()).data);
    const requested = await api.api26CreateVendorRequest({ path: vendorPath, body: { vendor_org_id: 1, vendor_message: "Another safe request" } });
    expect(requested.status).toBe(201); assertResponse("api26CreateVendorRequest", 201, requested.data);
  });
  it("manager directories, assignment and dashboard use canonical response shapes", async () => {
    await signIn("user@example.com"); const created = await api.api15CreateTicket({ body: { title: "Assign me", description: "Description", category: "NETWORK", priority: "LOW" } });
    await signIn("manager@example.com");
    assertResponse("api13ListAssignees", 200, (await api.api13ListAssignees({ query: { tier: "TIER2", is_available: true } })).data);
    assertResponse("api21AssignTicket", 200, (await api.api21AssignTicket({ path: { id: created.data.data.ticket_id }, body: { assignee_id: 2001 } })).data);
    assertResponse("api06DashboardSummary", 200, (await api.api06DashboardSummary()).data);
    const history = await api.api07OverdueTickets({ query: { mode: "history" } }); assertResponse("api07OverdueTickets", 200, history.data);
    expect(history.data.data).toHaveLength(1); expect(history.data.meta.mode).toBe("history");
    const current = await api.api07OverdueTickets({ query: { mode: "current" } }); assertResponse("api07OverdueTickets", 200, current.data);
    expect(current.data.data[0].is_current).toBe(true);
  });
  it("upload completion is idempotent and sends only upload_id", async () => {
    await signIn("user@example.com");
    const presign = await api.api02CreateAttachmentUpload({ path, body: { file_name: "test.log", content_type: "text/plain", size_bytes: 4, visibility: "USER_VISIBLE" } });
    assertResponse("api02CreateAttachmentUpload", 201, presign.data); const upload = presign.data.data;
    await expect(api.api03CompleteAttachmentUpload({ path, body: { upload_id: upload.upload_id } })).rejects.toMatchObject({ code: "UPLOAD_NOT_READY" });
    const put = await fetch(upload.upload_url, { method: "PUT", body: "test", headers: upload.signed_headers }); expect(put.status).toBe(200);
    const first = await api.api03CompleteAttachmentUpload({ path, body: { upload_id: upload.upload_id } }); const second = await api.api03CompleteAttachmentUpload({ path, body: { upload_id: upload.upload_id } });
    assertResponse("api03CompleteAttachmentUpload", 200, first.data); expect(first.data).toEqual(second.data);
    const list = await api.api04ListAttachments({ path }); assertResponse("api04ListAttachments", 200, list.data); expect(list.data.data).toHaveLength(1);
    assertResponse("api05GetAttachmentDownload", 200, (await api.api05GetAttachmentDownload({ path: { ...path, attachment_id: first.data.data.attachment_id } })).data);
    expect(mockState.attachments.get(5001)).toHaveLength(1);
  });
});
