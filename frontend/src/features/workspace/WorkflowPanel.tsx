import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "antd";
import * as api from "../../api/generated/sdk.gen";
import type { AvailableAction, TicketDetail } from "../../api/types";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";
import { normalizeApiError } from "../../api/errorHandler";
import { label, Pager, QueryNotice, useWorkspaceKey, useWrite } from "./shared";

export const actionLabels: Partial<Record<AvailableAction, string>> = {
  ASSIGN: "Assign / reassign", START: "Start handling", REQUEST_USER_INFO: "Request information", RESUME: "Provide information / issue persists",
  ESCALATE: "Escalate to Tier 2", REQUEST_VENDOR: "Request vendor support", VENDOR_RESPONSE: "Respond to request", RESOLVE: "Submit resolution",
  CONFIRM_RESOLUTION: "Confirm resolution", REOPEN: "Reopen ticket", CLOSE: "Close ticket",
};
type WorkflowAction = keyof typeof actionLabels;
export function WorkflowPanel({ ticket, action, onDone, onCancel }: { ticket: TicketDetail; action: WorkflowAction; onDone: (escalated: boolean) => void; onCancel: () => void }) {
  const key = useWorkspaceKey(); const write = useWrite(ticket.ticket_id); const [page, setPage] = useState(1); const [invalid, setInvalid] = useState("");
  const needsEngineer = action === "ASSIGN" || action === "ESCALATE";
  const tier2 = action === "ESCALATE" || ticket.sla?.status === "OVERDUE" || ticket.assignee?.tier === "TIER2";
  const engineers = useQuery({ queryKey: [...key, "assignees", ticket.category, tier2, page], enabled: needsEngineer,
    queryFn: async ({ signal }) => (await api.api13ListAssignees({ signal, query: { page, page_size: 20, is_available: true, category: ticket.category, tier: tier2 ? "TIER2" : undefined } })).data });
  const vendors = useQuery({ queryKey: [...key, "vendors", page], enabled: action === "REQUEST_VENDOR",
    queryFn: async ({ signal }) => (await api.api14ListVendors({ signal, query: { page, page_size: 20, is_active: true } })).data });
  const failureStatus = write.error ? normalizeApiError(write.error).status : undefined;
  // Conflicts require an explicit reread; do not silently repeat a write.
  useEffect(() => { setPage(1); }, [action]);
  const textRequired = ["REQUEST_USER_INFO", "RESUME", "REQUEST_VENDOR", "VENDOR_RESPONSE", "RESOLVE", "REOPEN"].includes(action);
  const textName = action === "RESOLVE" ? "Resolution summary" : action === "REQUEST_VENDOR" ? "Vendor-safe message" : ["ASSIGN", "ESCALATE", "REOPEN", "CLOSE"].includes(action) ? "Reason" : "Message";
  const max = ["ASSIGN", "ESCALATE", "CLOSE"].includes(action) ? 1000 : action === "RESOLVE" ? 5000 : 4000;
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = new FormData(event.currentTarget); const message = String(values.get("message") ?? "").trim();
    if (textRequired && !message) { setInvalid("Enter a message, not only spaces."); return; }
    if (message.length > max) { setInvalid(`Enter no more than ${max} characters.`); return; }
    if (action === "CLOSE" && values.get("acknowledge") !== "on") { setInvalid("Acknowledge that closing is permanent."); return; }
    setInvalid("");
    await write.run(async (signal) => {
      const options = { path: { id: ticket.ticket_id }, signal };
      switch (action) {
        case "ASSIGN": return api.api21AssignTicket({ ...options, body: { assignee_id: Number(values.get("engineer")), ...(message ? { reason: message } : {}) } });
        case "START": return api.api22StartTicket(options);
        case "REQUEST_USER_INFO": return api.api23RequestUserInfo({ ...options, body: { message } });
        case "RESUME": return api.api24ResumeTicket({ ...options, body: { message } });
        case "ESCALATE": return api.api25EscalateTicket({ ...options, body: { tier2_assignee_id: Number(values.get("engineer")), ...(message ? { reason: message } : {}) } });
        case "REQUEST_VENDOR": return api.api26CreateVendorRequest({ ...options, body: { vendor_org_id: Number(values.get("vendor")), vendor_message: message } });
        case "VENDOR_RESPONSE": return api.api27VendorResponse({ ...options, body: { message } });
        case "RESOLVE": return api.api28ResolveTicket({ ...options, body: { resolution_summary: message } });
        case "CONFIRM_RESOLUTION": return api.api29ConfirmResolution(options);
        case "REOPEN": return api.api30ReopenTicket({ ...options, body: { reason: message } });
        case "CLOSE": return api.api31CloseTicket({ ...options, body: { acknowledge: true, ...(message ? { reason: message } : {}) } });
        default: throw new Error("Unsupported workflow action");
      }
    }, () => onDone(action === "ESCALATE"));
  }
  return <section className="panel action-panel"><div className="panel-heading"><h2>{actionLabels[action]}</h2></div><div className="panel-body">
    {write.error != null && <ApiErrorNotice error={write.error} />}
    {(failureStatus === 409 || failureStatus === 404 || failureStatus === 403) && <p>The ticket may have changed or become unavailable. <Button onClick={() => onDone(false)}>Reload ticket</Button></p>}
    {invalid && <p role="alert">{invalid}</p>}
    {action === "REQUEST_VENDOR" && <p className="warning-note">Do not include the requester's name, email, user ID or other personal information. Write a separate vendor-safe message.</p>}
    {action === "CLOSE" && <p className="warning-note">Closing is permanent. You cannot reopen this ticket or add further comments or attachments.</p>}
    {needsEngineer && <QueryNotice query={engineers} />}{action === "REQUEST_VENDOR" && <QueryNotice query={vendors} />}
    <form className="work-form" onSubmit={submit}><fieldset disabled={write.busy || failureStatus === 409 || failureStatus === 404 || failureStatus === 403}>
      {needsEngineer && <><label>Engineer<select aria-label="Engineer" name="engineer" required key={page} defaultValue=""><option value="" disabled>Select eligible engineer</option>
        {engineers.data?.data.filter((e) => e.user_id !== ticket.assignee?.user_id).map((e) => <option key={e.user_id} value={e.user_id}>{e.display_name} · {e.tier} · load {e.active_load}</option>)}</select></label>
        {engineers.data && <Pager page={page} total={engineers.data.meta.total_pages} onChange={setPage} />}</>}
      {action === "REQUEST_VENDOR" && <><label>Vendor organisation<select aria-label="Vendor organisation" name="vendor" required key={page} defaultValue=""><option value="" disabled>Select organisation</option>{vendors.data?.data.map((v) => <option key={v.vendor_org_id} value={v.vendor_org_id}>{v.name}</option>)}</select></label>
        {vendors.data && <Pager page={page} total={vendors.data.meta.total_pages} onChange={setPage} />}</>}
      {!["START", "CONFIRM_RESOLUTION"].includes(action) && <label>{textName}{!textRequired && " (optional)"}<textarea name="message" rows={4} required={textRequired} maxLength={max} /></label>}
      {action === "CLOSE" && <label className="check-label"><input type="checkbox" name="acknowledge" required />I understand this action is irreversible.</label>}
      <div className="form-actions"><Button htmlType="submit" type="primary" danger={action === "CLOSE"} loading={write.busy}>{action === "CLOSE" ? "Confirm permanent close" : `Confirm ${label(action)}`}</Button><Button onClick={onCancel}>Cancel action</Button></div>
    </fieldset></form></div></section>;
}
