import type { TicketDetail, UserProfile } from "../api/generated/types.gen";
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
};

export function resetMockState(): void {
  mockState.accounts.clear();
  mockState.tokens.clear();
  mockState.tickets.clear();
  mockState.nextUserId = 1002;
  mockState.nextTicketId = 5002;
  const profile = structuredClone(fixtures.operations.api10GetMyProfile.body.data) as UserProfile;
  const ticket = structuredClone(fixtures.operations.api17GetTicket.body.data) as TicketDetail;
  // The contract examples show different actors. This baseline is a USER session,
  // so engineer-only buttons must not leak from the example into the USER view.
  ticket.available_actions = ["COMMENT", "UPLOAD_ATTACHMENT"];
  ticket.vendor_request = null;
  mockState.accounts.set(profile.email, { profile, password: mockCredentials.password });
  mockState.tickets.set(ticket.ticket_id, ticket);
}

resetMockState();
