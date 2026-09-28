import type { AvailableAction, TicketDetail, UserProfile } from "../api/types";

export function inScope(ticket: TicketDetail, user: UserProfile) {
  if (user.role === "USER") return ticket.requester?.user_id === user.user_id;
  if (user.role === "EXTERNAL_VENDOR") return ticket.vendor_request?.vendor_org.vendor_org_id === user.vendor_org?.vendor_org_id;
  return user.role === "SERVICE_DESK_MANAGER" || ticket.assignee?.user_id === user.user_id;
}
export function projectTicket(source: TicketDetail, user: UserProfile): TicketDetail {
  const ticket = structuredClone(source); const actions: AvailableAction[] = []; const status = source.status;
  if (!inScope(source, user)) return { ...ticket, available_actions: [] };
  if (user.role === "EXTERNAL_VENDOR") {
    const active = ticket.vendor_request?.status === "ACTIVE" && status !== "CLOSED";
    return { ...ticket, description: null, requester: null, assignee: null, sla: null, pending_user: null, resolution: null, closure: null,
      status: status === "CLOSED" ? "CLOSED" : active ? "PENDING_VENDOR" : "IN_PROGRESS",
      display_status: status === "CLOSED" ? "Closed" : active ? "Pending vendor" : "In progress", available_actions: active ? ["VENDOR_RESPONSE", "UPLOAD_ATTACHMENT"] : [] };
  }
  if (status !== "CLOSED") {
    if (!(user.role === "USER" && status === "PENDING_USER")) actions.push("COMMENT");
    actions.push("UPLOAD_ATTACHMENT");
    if (user.role === "USER") {
      if (status === "UNASSIGNED") actions.unshift("EDIT");
      if (status === "PENDING_USER") { actions.push("RESUME"); if (ticket.pending_user?.reason === "RESOLUTION_CONFIRMATION") actions.push("CONFIRM_RESOLUTION"); }
      if (status === "RESOLVED") actions.push("REOPEN", "CLOSE");
    } else if (user.role === "SERVICE_DESK_MANAGER") {
      actions.push("EDIT");
      if (status === "UNASSIGNED" || status === "PENDING_USER" || (status === "REOPENED" && !ticket.assignee) || (ticket.sla?.status === "OVERDUE" && ["ASSIGNED", "IN_PROGRESS", "PENDING_VENDOR"].includes(status))) actions.push("ASSIGN");
    } else {
      if (["ASSIGNED", "REOPENED"].includes(status)) actions.push("START");
      if (status === "IN_PROGRESS") {
        actions.push("REQUEST_USER_INFO", "RESOLVE");
        actions.push(user.role === "ENGINEER_TIER1" ? "ESCALATE" : "REQUEST_VENDOR");
      }
      if (status === "PENDING_VENDOR" && user.role === "ENGINEER_TIER2") actions.push("RESOLVE");
    }
  }
  if (user.role === "USER") {
    ticket.vendor_request = null;
    if (status === "PENDING_VENDOR") { ticket.status = "IN_PROGRESS"; ticket.display_status = "In progress"; }
  } else if (user.role === "ENGINEER_TIER1") ticket.vendor_request = null;
  return { ...ticket, available_actions: actions };
}
