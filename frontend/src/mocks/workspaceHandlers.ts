import { http, HttpResponse } from "msw";
import Ajv from "ajv/dist/2020";
import addFormats from "ajv-formats";
import type { Attachment, AvailableAction, Comment, DashboardCounts, ErrorCode, TicketDetail, TicketEvent, UserProfile, PresignRequest, VendorResponseView } from "../api/types";
import fixtures from "./workspace-fixtures.generated.json";
import { mockState } from "./state";
import { inScope, projectTicket } from "./workspaceModel";

const ajv = new Ajv({ strict: false, allErrors: true }); addFormats(ajv);
ajv.addFormat("int64", { type: "number", validate: Number.isSafeInteger }); ajv.addFormat("password", true);
type Operation = keyof typeof fixtures.operations;
const validators = new Map<string, ReturnType<typeof ajv.compile>>();
function validBody(operation: Operation, body: unknown) {
  const schema = fixtures.operations[operation].requestSchema;
  if (!schema) return body === undefined;
  let validate = validators.get(operation);
  if (!validate) { validate = ajv.compile({ ...schema, components: fixtures.components }); validators.set(operation, validate); }
  return validate(body);
}
const now = () => new Date().toISOString();
const after = (hours: number) => new Date(Date.now() + hours * 3600000).toISOString();
const staff = (user: UserProfile) => ["ENGINEER_TIER1", "ENGINEER_TIER2", "SERVICE_DESK_MANAGER"].includes(user.role);
const routes: Record<string, { action: AvailableAction; operation: Operation }> = {
  assign: { action: "ASSIGN", operation: "api21AssignTicket" }, start: { action: "START", operation: "api22StartTicket" },
  "request-user-info": { action: "REQUEST_USER_INFO", operation: "api23RequestUserInfo" }, resume: { action: "RESUME", operation: "api24ResumeTicket" },
  escalate: { action: "ESCALATE", operation: "api25EscalateTicket" }, "vendor-requests": { action: "REQUEST_VENDOR", operation: "api26CreateVendorRequest" },
  "vendor-response": { action: "VENDOR_RESPONSE", operation: "api27VendorResponse" }, resolve: { action: "RESOLVE", operation: "api28ResolveTicket" },
  "confirm-resolution": { action: "CONFIRM_RESOLUTION", operation: "api29ConfirmResolution" }, reopen: { action: "REOPEN", operation: "api30ReopenTicket" }, close: { action: "CLOSE", operation: "api31CloseTicket" },
};
const eventTypes: Partial<Record<AvailableAction, TicketEvent["event_type"]>> = {
  ASSIGN: "ASSIGNED", START: "HANDLING_STARTED", REQUEST_USER_INFO: "USER_INFO_REQUESTED", RESUME: "USER_RESUMED", ESCALATE: "REASSIGNED",
  REQUEST_VENDOR: "VENDOR_REQUESTED", VENDOR_RESPONSE: "VENDOR_RESPONDED", RESOLVE: "RESOLUTION_SUBMITTED", CONFIRM_RESOLUTION: "RESOLUTION_CONFIRMED", REOPEN: "TICKET_REOPENED", CLOSE: "TICKET_CLOSED_MANUAL",
};

// Deterministic UI sandbox, not a replacement for the transactional Python workflow.
export function createWorkspaceHandlers({ url, authenticatedUser, error }: {
  url: (path: string) => string; authenticatedUser: (request: Request) => UserProfile | undefined;
  error: (request: Request, status: number, code: ErrorCode, message: string) => Response;
}) {
  const json = (request: Request, body: Record<string, unknown>, status = 200) => HttpResponse.json(body, { status, headers: { "X-Request-ID": request.headers.get("X-Request-ID") ?? crypto.randomUUID() } });
  const denied = (request: Request) => error(request, 403, "DATA_SCOPE_DENIED", "This operation is not available to your role.");
  function actor(request: Request) { return authenticatedUser(request) ?? error(request, 401, "INVALID_ACCESS_TOKEN", "Sign in with a valid access token."); }
  const historyFor = (ticketId: number) => mockState.vendorHistories.get(ticketId) ?? [];
  const projected = (ticket: TicketDetail, user: UserProfile) => projectTicket(ticket, user, historyFor(ticket.ticket_id));
  function ticketFor(request: Request, id: number, user: UserProfile) { const ticket = mockState.tickets.get(id); return ticket && inScope(ticket, user, historyFor(id)) ? ticket : error(request, 404, "RESOURCE_NOT_FOUND", "Ticket not found."); }
  function paginate<T>(request: Request, data: T[]) {
    const search = new URL(request.url).searchParams; const page = Number(search.get("page") ?? 1); const size = Number(search.get("page_size") ?? 20);
    if (!Number.isInteger(page) || page < 1 || !Number.isInteger(size) || size < 1 || size > 100) return error(request, 422, "VALIDATION_ERROR", "Invalid pagination.");
    return json(request, { data: data.slice((page - 1) * size, page * size), meta: { page, page_size: size, total: data.length, total_pages: Math.ceil(data.length / size), ...(search.has("mode") ? { mode: search.get("mode") } : {}) } });
  }
  async function bodyFor(request: Request, operation: Operation) {
    let body: Record<string, unknown> | undefined;
    try { body = request.headers.get("content-type")?.includes("application/json") ? await request.json() : undefined; } catch { return error(request, 422, "VALIDATION_ERROR", "Invalid JSON."); }
    return validBody(operation, body) ? body ?? {} : error(request, 422, "VALIDATION_ERROR", "Check the request fields.");
  }
  function event(ticket: TicketDetail, user: UserProfile, type: TicketEvent["event_type"], scope: TicketEvent["scope"] = "USER_VISIBLE", metadata: TicketEvent["metadata"] = {}) {
    const entries = mockState.events.get(ticket.ticket_id) ?? []; const item: TicketEvent = { event_id: entries.length + 1, ticket_id: ticket.ticket_id, event_type: type, scope,
      actor: { user_id: user.user_id, display_name: user.display_name, role: user.role }, cycle_no: ticket.sla?.cycle_no ?? null, occurred_at: now(), metadata };
    entries.push(item); mockState.events.set(ticket.ticket_id, entries); return item.event_id;
  }
  function comment(ticket: TicketDetail, user: UserProfile, message: string, visibility: Comment["visibility"]) {
    const entries = mockState.comments.get(ticket.ticket_id) ?? []; const item: Comment = { comment_id: entries.length + 1, ticket_id: ticket.ticket_id,
      author: { user_id: user.user_id, display_name: user.display_name, role: user.role }, message, visibility, created_at: now() };
    entries.push(item); mockState.comments.set(ticket.ticket_id, entries); return item;
  }
  const engineers = () => [...mockState.accounts.values()].filter(({ profile }) => profile.role.startsWith("ENGINEER")).map(({ profile }) => ({ user_id: profile.user_id, display_name: profile.display_name,
    tier: profile.role === "ENGINEER_TIER1" ? "TIER1" as const : "TIER2" as const, skills: ["NETWORK", "HARDWARE", "SOFTWARE", "ACCOUNT", "OTHER"] as TicketDetail["category"][], is_available: profile.is_available === true,
    active_load: [...mockState.tickets.values()].filter((t) => t.assignee?.user_id === profile.user_id && ["ASSIGNED", "IN_PROGRESS", "PENDING_VENDOR", "REOPENED"].includes(t.status)).length }));
  return [
    http.get(url("/users/assignees"), ({ request }) => { const user = actor(request); if (user instanceof Response) return user; if (!staff(user)) return denied(request);
      const q = new URL(request.url).searchParams; return paginate(request, engineers().filter((e) => (!q.has("tier") || e.tier === q.get("tier")) && (!q.has("category") || e.skills.includes(q.get("category") as TicketDetail["category"])) && (!q.has("is_available") || String(e.is_available) === q.get("is_available")))); }),
    http.get(url("/vendors"), ({ request }) => { const user = actor(request); if (user instanceof Response) return user; if (!["ENGINEER_TIER2", "SERVICE_DESK_MANAGER"].includes(user.role)) return denied(request);
      const search = new URL(request.url).searchParams.get("search")?.toLowerCase() ?? "";
      return paginate(request, [{ vendor_org_id: 1, name: "Example Support Ltd", is_active: true }].filter((v) => v.name.toLowerCase().includes(search))); }),
    http.patch(url("/tickets/:id"), async ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      if (!projected(ticket, user).available_actions.includes("EDIT")) return denied(request);
      const body = await bodyFor(request, "api18UpdateTicket"); if (body instanceof Response) return body; if (!Object.keys(body).length) return error(request, 422, "VALIDATION_ERROR", "Provide at least one field.");
      Object.assign(ticket, body, { updated_at: now() }); return json(request, { data: projected(ticket, user) }); }),
    http.get(url("/tickets/:id/vendor-requests"), ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      if (!["ENGINEER_TIER2", "SERVICE_DESK_MANAGER", "EXTERNAL_VENDOR"].includes(user.role)) return denied(request);
      const history = historyFor(ticket.ticket_id).filter((item) => user.role !== "EXTERNAL_VENDOR" || item.vendor_org.vendor_org_id === user.vendor_org?.vendor_org_id);
      return json(request, { data: structuredClone(history) }); }),
    http.get(url("/tickets/:id/comments"), ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      if (user.role === "EXTERNAL_VENDOR") return denied(request); return paginate(request, (mockState.comments.get(ticket.ticket_id) ?? []).filter((c) => user.role !== "USER" || c.visibility === "USER_VISIBLE")); }),
    http.post(url("/tickets/:id/comments"), async ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      if (!projected(ticket, user).available_actions.includes("COMMENT")) return error(request, 409, "INVALID_STATUS_TRANSITION", "Use the available workflow action instead of a comment.");
      const body = await bodyFor(request, "api20CreateComment"); if (body instanceof Response) return body; if (user.role === "USER" && body.visibility !== "USER_VISIBLE") return denied(request);
      const item = comment(ticket, user, String(body.message), body.visibility as Comment["visibility"]); event(ticket, user, "COMMENT_ADDED", item.visibility, { comment_id: item.comment_id }); return json(request, { data: item }, 201); }),
    ...Object.entries(routes).map(([route, { action, operation }]) => http.post(url(`/tickets/:id/${route}`), async ({ request, params }) => {
      const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      if (!projected(ticket, user).available_actions.includes(action)) return error(request, 409, "INVALID_STATUS_TRANSITION", "This action is no longer available. Reload the ticket.");
      const body = await bodyFor(request, operation); if (body instanceof Response) return body;
      if (ticket.pending_user && ["RESUME", "CONFIRM_RESOLUTION"].includes(action) && Date.parse(ticket.pending_user.deadline) <= Date.now()) return error(request, 409, "USER_RESPONSE_WINDOW_EXPIRED", "The response window has expired.");
      if (["REOPEN", "CLOSE"].includes(action) && ticket.resolution?.auto_close_at && Date.parse(ticket.resolution.auto_close_at) <= Date.now()) return error(request, 409, "INVALID_STATUS_TRANSITION", "The reopen window has expired.");
      let commentId: number | null = null;
      if (action === "ASSIGN" || action === "ESCALATE") {
        const engineer = engineers().find((e) => e.user_id === Number(body.assignee_id ?? body.tier2_assignee_id));
        const tier2 = action === "ESCALATE" || ticket.sla?.status === "OVERDUE" || ticket.assignee?.tier === "TIER2";
        if (!engineer?.is_available || !engineer.skills.includes(ticket.category) || (tier2 && engineer.tier !== "TIER2") || engineer.user_id === ticket.assignee?.user_id) return error(request, 409, "ASSIGNEE_NOT_ELIGIBLE", "Select another eligible engineer.");
        ticket.assignee = engineer; if (!["PENDING_USER", "PENDING_VENDOR"].includes(ticket.status)) ticket.status = "ASSIGNED";
      }
      if (action === "START") ticket.status = "IN_PROGRESS";
      if (action === "REQUEST_USER_INFO" || action === "RESOLVE") {
        ticket.status = "PENDING_USER"; ticket.pending_user = { reason: action === "RESOLVE" ? "RESOLUTION_CONFIRMATION" : "INFORMATION_REQUIRED", deadline: after(120) };
        if (ticket.sla) ticket.sla.status = action === "RESOLVE" ? (ticket.sla.status === "OVERDUE" ? "OVERDUE" : "MET") : "PAUSED";
        commentId = comment(ticket, user, String(body.message ?? body.resolution_summary), "USER_VISIBLE").comment_id;
        if (action === "RESOLVE") { ticket.resolution = { summary: String(body.resolution_summary), type: null, resolved_at: null, auto_close_at: null }; if (ticket.vendor_request?.status === "ACTIVE") {
          ticket.vendor_request.status = "CANCELLED"; const current = historyFor(ticket.ticket_id).find((item) => item.vendor_request_id === ticket.vendor_request?.vendor_request_id); if (current) current.status = "CANCELLED";
        } }
      }
      if (action === "RESUME" || action === "REOPEN") {
        ticket.status = action === "REOPEN" ? "REOPENED" : "IN_PROGRESS"; ticket.pending_user = null; ticket.resolution = null;
        ticket.sla = { cycle_no: (ticket.sla?.cycle_no ?? 0) + 1, status: "ON_TRACK", started_at: now(), deadline: after(48) };
        commentId = comment(ticket, user, String(body.message ?? body.reason), "USER_VISIBLE").comment_id;
      }
      if (action === "CONFIRM_RESOLUTION") { ticket.status = "RESOLVED"; ticket.pending_user = null; ticket.resolution = { summary: ticket.resolution?.summary ?? "", type: "USER_CONFIRMED", resolved_at: now(), auto_close_at: after(168) }; }
      if (action === "CLOSE") { ticket.status = "CLOSED"; ticket.closure = { type: "MANUAL_USER", closed_at: now() }; }
      if (action === "REQUEST_VENDOR") {
        if (body.vendor_org_id !== 1) return error(request, 404, "RESOURCE_NOT_FOUND", "Vendor not found.");
        const history = historyFor(ticket.ticket_id); const requestId = Math.max(0, ...history.map((item) => item.vendor_request_id)) + 1;
        ticket.status = "PENDING_VENDOR"; ticket.vendor_request = { vendor_request_id: requestId, vendor_org: { vendor_org_id: 1, name: "Example Support Ltd", is_active: true }, status: "ACTIVE", vendor_message: String(body.vendor_message), created_at: now(), responded_at: null };
        history.push({ ...ticket.vendor_request, response: null }); mockState.vendorHistories.set(ticket.ticket_id, history);
      }
      if (action === "VENDOR_RESPONSE") { ticket.status = "IN_PROGRESS"; ticket.vendor_request!.status = "RESPONDED"; ticket.vendor_request!.responded_at = now(); }
      ticket.updated_at = now(); ticket.display_status = ticket.status.toLowerCase().replaceAll("_", " ");
      const scope = action === "REQUEST_VENDOR" || action === "VENDOR_RESPONSE" ? "VENDOR_SCOPE" : "USER_VISIBLE";
      // The backend records an empty audit metadata object, not the reply body.
      // API-33 reads persisted request/response bodies from the separate history store.
      const eventId = event(ticket, user, eventTypes[action]!, scope, {});
      let vendorResponse: VendorResponseView | null = null;
      if (action === "VENDOR_RESPONSE") {
        vendorResponse = { vendor_response_id: eventId, vendor_request_id: ticket.vendor_request!.vendor_request_id, message: String(body.message), created_at: now() };
        const current = historyFor(ticket.ticket_id).find((item) => item.vendor_request_id === ticket.vendor_request?.vendor_request_id);
        if (current) { current.status = "RESPONDED"; current.responded_at = ticket.vendor_request!.responded_at; current.response = vendorResponse; }
      }
      const responseTicket = projected(ticket, user);
      return json(request, { data: { action, ticket: responseTicket, event_id: eventId, comment_id: commentId, vendor_request: responseTicket.vendor_request,
        vendor_response: vendorResponse } }, fixtures.operations[operation].status);
    })),
    http.get(url("/tickets/:id/events"), ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      return paginate(request, (mockState.events.get(ticket.ticket_id) ?? []).filter((e) => user.role === "USER" ? e.scope === "USER_VISIBLE" : user.role === "EXTERNAL_VENDOR" ? e.scope === "VENDOR_SCOPE" : user.role === "ENGINEER_TIER1" ? e.scope !== "VENDOR_SCOPE" : true)); }),
    http.get(url("/tickets/:id/attachments"), ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      return paginate(request, (mockState.attachments.get(ticket.ticket_id) ?? []).filter((a) => user.role === "USER" ? a.visibility === "USER_VISIBLE" : user.role === "EXTERNAL_VENDOR" ? a.visibility === "VENDOR_SHARED" : user.role === "ENGINEER_TIER1" ? a.visibility !== "VENDOR_SHARED" : true)); }),
    http.post(url("/tickets/:id/attachments/presign"), async ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      if (!projected(ticket, user).available_actions.includes("UPLOAD_ATTACHMENT")) return denied(request);
      const body = await bodyFor(request, "api02CreateAttachmentUpload"); if (body instanceof Response) return body;
      if ((user.role === "USER" && body.visibility !== "USER_VISIBLE") || (user.role === "EXTERNAL_VENDOR" && body.visibility !== "VENDOR_SHARED") || (user.role === "ENGINEER_TIER1" && body.visibility === "VENDOR_SHARED")) return denied(request);
      if (body.visibility === "VENDOR_SHARED" && ticket.vendor_request?.status !== "ACTIVE") return error(request, 409, "NO_ACTIVE_VENDOR_REQUEST", "An active vendor request is required.");
      const uploadId = crypto.randomUUID(); mockState.uploads.set(uploadId, { ticketId: ticket.ticket_id, userId: user.user_id, body: body as PresignRequest, uploaded: false });
      return json(request, { data: { upload_id: uploadId, upload_url: url(`/mock-storage/${uploadId}`), method: "PUT", signed_headers: { "Content-Type": body.content_type }, expires_at: after(0.25), max_size_bytes: 10485760 } }, 201); }),
    http.put(url("/mock-storage/:uploadId"), async ({ request, params }) => { const upload = mockState.uploads.get(String(params.uploadId)); if (!upload) return new HttpResponse(null, { status: 404 });
      if (request.headers.has("Authorization")) return new HttpResponse(null, { status: 400 });
      const bytes = await request.arrayBuffer(); if (bytes.byteLength !== upload.body.size_bytes || request.headers.get("content-type") !== upload.body.content_type) return new HttpResponse(null, { status: 400 });
      upload.uploaded = true; return new HttpResponse(null, { status: 200 }); }),
    http.post(url("/tickets/:id/attachments/complete"), async ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      const body = await bodyFor(request, "api03CompleteAttachmentUpload"); if (body instanceof Response) return body; const upload = mockState.uploads.get(String(body.upload_id));
      if (!upload || upload.userId !== user.user_id || upload.ticketId !== ticket.ticket_id) return error(request, 404, "RESOURCE_NOT_FOUND", "Upload not found.");
      if (upload.attachment) return json(request, { data: upload.attachment });
      if (!projected(ticket, user).available_actions.includes("UPLOAD_ATTACHMENT")) return denied(request);
      if (!upload.uploaded) return error(request, 409, "UPLOAD_NOT_READY", "The file has not been uploaded yet.");
      const attachment: Attachment = { ...upload.body, attachment_id: crypto.randomUUID(), ticket_id: ticket.ticket_id, created_at: now() }; upload.attachment = attachment;
      mockState.attachments.set(ticket.ticket_id, [...mockState.attachments.get(ticket.ticket_id) ?? [], attachment]); event(ticket, user, "ATTACHMENT_ADDED", attachment.visibility === "VENDOR_SHARED" ? "VENDOR_SCOPE" : attachment.visibility);
      return json(request, { data: attachment }); }),
    http.get(url("/tickets/:id/attachments/:attachmentId/download"), ({ request, params }) => { const user = actor(request); if (user instanceof Response) return user; const ticket = ticketFor(request, Number(params.id), user); if (ticket instanceof Response) return ticket;
      const item = mockState.attachments.get(ticket.ticket_id)?.find((a) => a.attachment_id === params.attachmentId);
      if (!item || (user.role === "USER" && item.visibility !== "USER_VISIBLE") || (user.role === "EXTERNAL_VENDOR" && item.visibility !== "VENDOR_SHARED") || (user.role === "ENGINEER_TIER1" && item.visibility === "VENDOR_SHARED")) return error(request, 404, "RESOURCE_NOT_FOUND", "Attachment not found.");
      return json(request, { data: { attachment_id: item.attachment_id, file_name: item.file_name, content_type: item.content_type, download_url: new URL("/mock-download.txt", globalThis.location?.origin ?? url("")).href, expires_at: after(5 / 60) } }); }),
    http.get(url("/dashboard/summary"), ({ request }) => { const user = actor(request); if (user instanceof Response) return user; if (!staff(user)) return denied(request);
      const tickets = [...mockState.tickets.values()].filter((t) => inScope(t, user, historyFor(t.ticket_id))); const counts: DashboardCounts = { total_active: 0, unassigned: 0, assigned: 0, in_progress: 0, pending_user: 0, pending_vendor: 0, resolved: 0, reopened: 0, closed: 0 };
      for (const t of tickets) { counts[t.status.toLowerCase() as Exclude<keyof DashboardCounts, "total_active">]++; if (!["CLOSED", "RESOLVED"].includes(t.status)) counts.total_active++; }
      return json(request, { data: { scope: user.role === "SERVICE_DESK_MANAGER" ? "GLOBAL" : "MY_ASSIGNED", generated_at: now(), counts,
        sla: { at_risk: tickets.filter((t) => t.sla?.status === "AT_RISK").length, overdue: tickets.filter((t) => t.sla?.status === "OVERDUE").length }, action_required: { reopened_unassigned: tickets.filter((t) => t.status === "REOPENED" && !t.assignee).length } } }); }),
    http.get(url("/dashboard/overdue-tickets"), ({ request }) => { const user = actor(request); if (user instanceof Response) return user; if (!staff(user)) return denied(request);
      const q = new URL(request.url).searchParams;
      // No clock-driven scheduler in this sandbox; history comes from explicitly seeded events.
      const rows = [...mockState.tickets.values()].filter((t) => inScope(t, user, historyFor(t.ticket_id)) && (!q.has("category") || t.category === q.get("category")) && (!q.has("priority") || t.priority === q.get("priority"))).flatMap((t) => {
        const cycles = q.get("mode") === "history" ? (mockState.events.get(t.ticket_id) ?? []).filter((e) => e.event_type === "SLA_OVERDUE").map((e) => ({ cycle: e.cycle_no ?? 1, at: e.occurred_at })) : t.sla?.status === "OVERDUE" ? [{ cycle: t.sla.cycle_no, at: t.sla.deadline! }] : [];
        return cycles.map((c) => ({ ticket_id: t.ticket_id, title: t.title, category: t.category, priority: t.priority, status: t.status, display_status: t.display_status, assignee: t.assignee, sla_cycle_no: c.cycle, sla_deadline: c.at, overdue_at: c.at, is_current: t.sla?.status === "OVERDUE" && t.sla.cycle_no === c.cycle }));
      }); return paginate(request, rows); }),
  ];
}
