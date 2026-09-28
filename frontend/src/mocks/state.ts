import type { TicketDetail, UserProfile, Comment, Attachment, TicketEvent, PresignRequest, Role } from "../api/generated/types.gen";
import fixtures from "./fixtures.generated.json";

// Deliberately fake credentials, usable only by the local MSW implementation.
export const mockCredentials = { email: "user@example.com", password: "MockPass123!" };
type MockAccount = { profile: UserProfile; password: string };

export const mockState = {
  accounts: new Map<string, MockAccount>(),
  tokens: new Map<string, { userId: number; expiresAt: number }>(),
  tickets: new Map<number, TicketDetail>(),
  nextUserId: 1002,
  nextTicketId: 5002,
  comments: new Map<number, Comment[]>(),
  attachments: new Map<number, Attachment[]>(),
  events: new Map<number, TicketEvent[]>(),
  uploads: new Map<string, { ticketId: number; userId: number; body: PresignRequest; uploaded: boolean; attachment?: Attachment }>(),
};
export const demoRoles: { role: Role; email: string; id: number; name: string }[] = [
  { role: "ENGINEER_TIER1", email: "tier1@example.com", id: 2001, name: "Tier 1 Engineer" },
  { role: "ENGINEER_TIER2", email: "tier2@example.com", id: 2002, name: "Tier 2 Engineer" },
  { role: "EXTERNAL_VENDOR", email: "vendor@example.com", id: 3001, name: "Example Vendor" },
  { role: "SERVICE_DESK_MANAGER", email: "manager@example.com", id: 4001, name: "Service Desk Manager" },
];

export function resetMockState(): void {
  mockState.accounts.clear();
  mockState.tokens.clear();
  mockState.tickets.clear();
  mockState.comments.clear(); mockState.attachments.clear(); mockState.events.clear(); mockState.uploads.clear();
  mockState.nextUserId = 1002;
  mockState.nextTicketId = 5002;
  const profile = structuredClone(fixtures.operations.api10GetMyProfile.body.data) as UserProfile;
  const ticket = structuredClone(fixtures.operations.api17GetTicket.body.data) as TicketDetail;
  // The contract examples show different actors. This baseline is a USER session,
  // so engineer-only buttons must not leak from the example into the USER view.
  ticket.available_actions = ["COMMENT", "UPLOAD_ATTACHMENT"];
  ticket.vendor_request = null;
  mockState.accounts.set(profile.email, { profile, password: mockCredentials.password });
  for (const actor of demoRoles) mockState.accounts.set(actor.email, { password: mockCredentials.password, profile: {
    ...profile, user_id: actor.id, email: actor.email, role: actor.role, display_name: actor.name,
    is_available: actor.role.startsWith("ENGINEER") ? true : null,
    vendor_org: actor.role === "EXTERNAL_VENDOR" ? { vendor_org_id: 1, name: "Example Support Ltd", is_active: true } : null,
  } });
  mockState.tickets.set(ticket.ticket_id, ticket);
  const vendorTicket: TicketDetail = { ...structuredClone(ticket), ticket_id: 6001, title: "Router firmware investigation", requester: { user_id: 1009, display_name: "Other requester" },
    status: "PENDING_VENDOR", display_status: "Pending vendor", assignee: { ...ticket.assignee!, user_id: 2002, display_name: "Tier 2 Engineer", tier: "TIER2" },
    vendor_request: { vendor_request_id: 1, vendor_org: { vendor_org_id: 1, name: "Example Support Ltd", is_active: true }, status: "ACTIVE", vendor_message: "Please review firmware version 4 connectivity logs.", created_at: new Date().toISOString(), responded_at: null } };
  mockState.tickets.set(6001, vendorTicket);
  const deadline = new Date(Date.now() - 3600000).toISOString();
  const overdue: TicketDetail = { ...structuredClone(ticket), ticket_id: 6002, title: "Overdue network switch inspection", requester: { user_id: 1009, display_name: "Other requester" },
    status: "UNASSIGNED", display_status: "Unassigned", assignee: null, sla: { cycle_no: 1, status: "OVERDUE", started_at: new Date(Date.now() - 49 * 3600000).toISOString(), deadline } };
  mockState.tickets.set(6002, overdue);
  mockState.events.set(6002, [{ event_id: 1, ticket_id: 6002, event_type: "SLA_OVERDUE", scope: "INTERNAL_ONLY", actor: null, cycle_no: 1, occurred_at: deadline, metadata: {} }]);
}

resetMockState();
