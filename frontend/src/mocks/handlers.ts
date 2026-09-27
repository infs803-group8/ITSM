import { http, HttpResponse } from "msw";
import type {
  ErrorBody, ErrorCode, ErrorResponse, LoginRequest, LoginResponse, ReferenceDataResponse, RegisterRequest,
  TicketCreateRequest, TicketDetail, TicketDetailResponse, TicketListResponse,
  TicketSummary, UpdateProfileRequest, UserProfile, UserResponse,
} from "../api/types";
import { apiBaseUrl } from "../api/config";
import fixtures from "./fixtures.generated.json";
import { mockState } from "./state";
import { validateBody, validateQuery, type MockOperation } from "./validation";
import { inScope, projectTicket } from "./workspaceModel";
import { createWorkspaceHandlers } from "./workspaceHandlers";

export const mockApiBaseUrl = new URL(apiBaseUrl, globalThis.location?.origin ?? "http://localhost:5173").href.replace(/\/+$/, "");
export const mockApiUrl = (route: string) => `${mockApiBaseUrl}${route}`;

function headers(request: Request): Record<string, string> {
  return { "X-Request-ID": request.headers.get("X-Request-ID") || crypto.randomUUID() };
}

export function mockError(request: Request, status: number, code: ErrorCode, message: string, details: ErrorBody["details"] = {}) {
  const responseHeaders = headers(request);
  return HttpResponse.json({ error: { code, message, details, request_id: responseHeaders["X-Request-ID"] } } satisfies ErrorResponse,
    { status, headers: responseHeaders });
}

function authenticatedUser(request: Request): UserProfile | undefined {
  const token = request.headers.get("Authorization")?.replace(/^Bearer /, "");
  const session = token ? mockState.tokens.get(token) : undefined;
  if (!session || session.expiresAt <= Date.now()) return undefined;
  return [...mockState.accounts.values()].find(({ profile }) => profile.user_id === session.userId)?.profile;
}

const unauthorized = (request: Request) => mockError(request, 401, "INVALID_ACCESS_TOKEN", "Sign in with a valid access token.");
const notFound = (request: Request) => mockError(request, 404, "RESOURCE_NOT_FOUND", "Ticket not found.");

async function readBody<T>(operation: MockOperation, request: Request): Promise<T | Response> {
  let body: unknown;
  try { body = await request.json(); } catch {
    return mockError(request, 422, "VALIDATION_ERROR", "A JSON request body is required.");
  }
  const errors = validateBody(operation, body);
  if (errors) {
    return mockError(request, 422, "VALIDATION_ERROR", "Check the request fields.", {
      fields: errors.map((error) => ({ path: error.instancePath, rule: error.keyword })),
    });
  }
  // Runtime schema validation above is generated from the same contract as T.
  return body as T;
}

function ticketSummary(ticket: TicketDetail): TicketSummary {
  return {
    ticket_id: ticket.ticket_id, title: ticket.title, category: ticket.category,
    priority: ticket.priority, status: ticket.status, display_status: ticket.display_status,
    assignee: ticket.assignee, sla: ticket.sla, available_actions: ticket.available_actions,
    created_at: ticket.created_at, updated_at: ticket.updated_at,
  };
}

export const handlers = [
  http.get(mockApiUrl("/health"), ({ request }) =>
    HttpResponse.json(fixtures.operations.api01Health.body, { headers: headers(request) })),

  http.post(mockApiUrl("/auth/register"), async ({ request }) => {
    const body = await readBody<RegisterRequest>("api08Register", request);
    if (body instanceof Response) return body;
    const email = body.email.toLowerCase();
    if (mockState.accounts.has(email)) return mockError(request, 409, "EMAIL_ALREADY_REGISTERED", "This email is already registered.");
    const profile: UserProfile = {
      user_id: mockState.nextUserId++, email, display_name: body.display_name, role: "USER",
      is_available: null, vendor_org: null, created_at: new Date().toISOString(),
    };
    mockState.accounts.set(email, { profile, password: body.password });
    return HttpResponse.json({ data: profile } satisfies UserResponse, { status: 201, headers: headers(request) });
  }),

  http.post(mockApiUrl("/auth/login"), async ({ request }) => {
    const body = await readBody<LoginRequest>("api09Login", request);
    if (body instanceof Response) return body;
    const account = mockState.accounts.get(body.email.toLowerCase());
    if (!account || account.password !== body.password) return mockError(request, 401, "INVALID_CREDENTIALS", "The email or password is incorrect.");
    const token = `mock-only-${crypto.randomUUID()}`;
    mockState.tokens.set(token, { userId: account.profile.user_id, expiresAt: Date.now() + 3_600_000 });
    return HttpResponse.json({ data: {
      access_token: token, token_type: "bearer", expires_in: 3600, user: account.profile,
    } } satisfies LoginResponse, { headers: headers(request) });
  }),

  http.get(mockApiUrl("/users/me"), ({ request }) => {
    const user = authenticatedUser(request);
    return user ? HttpResponse.json({ data: user } satisfies UserResponse, { headers: headers(request) }) : unauthorized(request);
  }),

  http.patch(mockApiUrl("/users/me"), async ({ request }) => {
    const user = authenticatedUser(request);
    if (!user) return unauthorized(request);
    const body = await readBody<UpdateProfileRequest>("api11UpdateMyProfile", request);
    if (body instanceof Response) return body;
    if (Object.keys(body).length === 0) return mockError(request, 422, "VALIDATION_ERROR", "Provide at least one profile field.");
    if (body.is_available !== undefined && !user.role.startsWith("ENGINEER")) return mockError(request, 403, "DATA_SCOPE_DENIED", "Only engineers can change availability.");
    if (body.is_available !== undefined) user.is_available = body.is_available;
    if (body.display_name !== undefined) user.display_name = body.display_name;
    return HttpResponse.json({ data: user } satisfies UserResponse, { headers: headers(request) });
  }),

  http.get(mockApiUrl("/reference-data"), ({ request }) => {
    const user = authenticatedUser(request);
    if (!user) return unauthorized(request);
    // The canonical example includes internal options. Project a fresh copy for
    // the baseline USER session; never mutate the shared generated fixture.
    const body = structuredClone(fixtures.operations.api12ReferenceData.body) as ReferenceDataResponse;
    if (user.role === "USER") {
      body.data.ticket_statuses = body.data.ticket_statuses.filter((status) => status !== "PENDING_VENDOR");
      body.data.comment_visibilities = ["USER_VISIBLE"];
      body.data.attachment_visibilities = ["USER_VISIBLE"];
    }
    if (user.role === "ENGINEER_TIER1") body.data.attachment_visibilities = ["USER_VISIBLE", "INTERNAL_ONLY"];
    if (user.role === "EXTERNAL_VENDOR") { body.data.ticket_statuses = ["PENDING_VENDOR", "IN_PROGRESS", "CLOSED"]; body.data.comment_visibilities = []; body.data.attachment_visibilities = ["VENDOR_SHARED"]; }
    return HttpResponse.json(body, { headers: headers(request) });
  }),

  http.post(mockApiUrl("/tickets"), async ({ request }) => {
    const user = authenticatedUser(request);
    if (!user) return unauthorized(request);
    if (user.role !== "USER") return mockError(request, 403, "DATA_SCOPE_DENIED", "Only requesters can create tickets.");
    const body = await readBody<TicketCreateRequest>("api15CreateTicket", request);
    if (body instanceof Response) return body;
    const now = new Date().toISOString();
    // Deterministic "no eligible engineer" branch. No SLA/assignment algorithm is simulated.
    const ticket: TicketDetail = {
      ticket_id: mockState.nextTicketId++, ...body, status: "UNASSIGNED", display_status: "Unassigned",
      requester: { user_id: user.user_id, display_name: user.display_name }, assignee: null,
      sla: null, pending_user: null, resolution: null, closure: null, vendor_request: null,
      available_actions: ["EDIT", "COMMENT", "UPLOAD_ATTACHMENT"], created_at: now, updated_at: now,
    };
    mockState.tickets.set(ticket.ticket_id, ticket);
    return HttpResponse.json({ data: ticket } satisfies TicketDetailResponse, { status: 201, headers: headers(request) });
  }),

  http.get(mockApiUrl("/tickets"), ({ request }) => {
    const user = authenticatedUser(request);
    if (!user) return unauthorized(request);
    const query = new URL(request.url).searchParams;
    if (validateQuery("api16ListTickets", query)) return mockError(request, 422, "VALIDATION_ERROR", "Check the filter and pagination values.");
    if (user.role === "USER" && query.get("status") === "PENDING_VENDOR") {
      return mockError(request, 403, "DATA_SCOPE_DENIED", "The requested status is not visible.");
    }
    if (query.has("assignee_id") && user.role !== "SERVICE_DESK_MANAGER") return mockError(request, 403, "DATA_SCOPE_DENIED", "Assignee filtering is restricted for this role.");
    if (user.role === "EXTERNAL_VENDOR" && query.has("status") && !["PENDING_VENDOR", "IN_PROGRESS", "CLOSED"].includes(query.get("status")!)) return mockError(request, 403, "DATA_SCOPE_DENIED", "The requested status is not visible.");
    let tickets = [...mockState.tickets.values()].filter((ticket) => inScope(ticket, user)).map((ticket) => projectTicket(ticket, user));
    if (query.has("assignee_id")) tickets = tickets.filter((t) => t.assignee?.user_id === Number(query.get("assignee_id")));
    for (const field of ["status", "category", "priority"] as const) {
      if (query.has(field)) tickets = tickets.filter((ticket) => ticket[field] === query.get(field));
    }
    if (query.has("sla_status")) tickets = tickets.filter((ticket) => ticket.sla?.status === query.get("sla_status"));
    if (query.has("search")) tickets = tickets.filter((ticket) => ticket.title.toLowerCase().includes(query.get("search")!.toLowerCase()));
    const sort = query.get("sort_by") ?? "created_at";
    const direction = query.get("sort_order") === "asc" ? 1 : -1;
    const priority = { LOW: 0, MEDIUM: 1, HIGH: 2, URGENT: 3 };
    const sortValue = (ticket: TicketDetail) => sort === "priority" ? priority[ticket.priority]
      : sort === "sla_deadline" ? ticket.sla?.deadline ?? ""
        : sort === "updated_at" ? ticket.updated_at : ticket.created_at;
    tickets.sort((a, b) => {
      const left = sortValue(a), right = sortValue(b);
      return (left < right ? -1 : left > right ? 1 : a.ticket_id - b.ticket_id) * direction;
    });
    const page = Number(query.get("page") ?? 1), pageSize = Number(query.get("page_size") ?? 20);
    return HttpResponse.json({
      data: tickets.slice((page - 1) * pageSize, page * pageSize).map(ticketSummary),
      meta: { page, page_size: pageSize, total: tickets.length, total_pages: Math.ceil(tickets.length / pageSize) },
    } satisfies TicketListResponse, { headers: headers(request) });
  }),

  http.get(mockApiUrl("/tickets/:id"), ({ request, params }) => {
    const user = authenticatedUser(request);
    if (!user) return unauthorized(request);
    const ticket = mockState.tickets.get(Number(params.id));
    if (!ticket || !inScope(ticket, user)) return notFound(request);
    return HttpResponse.json({ data: projectTicket(ticket, user) } satisfies TicketDetailResponse, { headers: headers(request) });
  }),

  ...createWorkspaceHandlers({ url: mockApiUrl, authenticatedUser, error: mockError }),

  // Baseline mocks must never silently send an unsupported API call to a real backend.
  http.all(mockApiUrl("/*"), () => HttpResponse.error()),
];
