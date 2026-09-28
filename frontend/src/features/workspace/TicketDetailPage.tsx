import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "antd";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api17GetTicket, api32ListEvents } from "../../api/generated/sdk.gen";
import type { AvailableAction } from "../../api/types";
import { normalizeApiError } from "../../api/errorHandler";
import { useAuth } from "../auth/AuthProvider";
import { AttachmentsPanel } from "./AttachmentsPanel";
import { CommentsPanel } from "./CommentsPanel";
import { TicketForm } from "./TicketForm";
import { actionLabels, WorkflowPanel } from "./WorkflowPanel";
import { date, label, PageHeading, Pager, QueryNotice, Status, useWorkspaceKey } from "./shared";

function EventsPanel({ id }: { id: number }) {
  const key = useWorkspaceKey(); const [page, setPage] = useState(1);
  const query = useQuery({ queryKey: [...key, "ticket", id, "events", page], queryFn: async ({ signal }) => (await api32ListEvents({ path: { id }, query: { page, page_size: 20 }, signal })).data });
  return <section className="panel"><div className="panel-heading"><h2>Activity timeline</h2><p>Only events visible to your role are returned.</p></div><div className="panel-body"><QueryNotice query={query} />
    {query.data && !query.error && <>{query.data.data.map((event) => <article className="thread-entry" key={event.event_id}><strong>{label(event.event_type)}</strong><small>{date(event.occurred_at)} · {event.actor?.display_name ?? "System"}{event.cycle_no != null && ` · Cycle ${event.cycle_no}`}</small>
      {Object.entries(event.metadata).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value)).map(([name, value]) => <p key={name}>{label(name)}: {String(value)}</p>)}</article>)}
      {!query.data.data.length && <p>No activity yet.</p>}<Pager page={page} total={query.data.meta.total_pages} onChange={setPage} /></>}
  </div></section>;
}
export function TicketDetailPage() {
  const { id: rawId } = useParams(); const id = Number(rawId); const valid = Number.isSafeInteger(id) && id > 0;
  const key = useWorkspaceKey(); const { user } = useAuth(); const navigate = useNavigate(); const client = useQueryClient();
  const [action, setAction] = useState<AvailableAction | null>(null); const [tab, setTab] = useState("comments"); const [notice, setNotice] = useState("");
  const query = useQuery({ queryKey: [...key, "ticket", id], enabled: valid, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false,
    queryFn: async ({ signal }) => (await api17GetTicket({ path: { id }, signal })).data.data });
  const inaccessible = query.error && [403, 404].includes(normalizeApiError(query.error).status ?? 0);
  useEffect(() => { if (inaccessible) {
    client.removeQueries({ queryKey: [...key, "ticket", id] });
    navigate("/tickets", { replace: true, state: { notice: "This ticket is no longer available to your account." } });
  } }, [inaccessible, id, client, navigate, key[1], key[2]]);
  useEffect(() => { setAction(null); setNotice(""); setTab("comments"); }, [id]);
  const vendor = user?.role === "EXTERNAL_VENDOR";
  function reload(escalated = false) {
    if (escalated && user?.role === "ENGINEER_TIER1") {
      client.removeQueries({ queryKey: [...key, "ticket", id] });
      navigate("/tickets", { replace: true, state: { notice: "Ticket escalated to Tier 2. It is no longer in your assigned queue." } }); return;
    }
    setAction(null); setNotice("Ticket updated."); void client.invalidateQueries({ queryKey: [...key, "ticket", id] });
  }
  if (!valid) return <><PageHeading title="Invalid ticket address" /><Link to="/tickets">Return to tickets</Link></>;
  const ticket = query.data;
  return <><Link className="back-link" to="/tickets">← Back to tickets</Link><QueryNotice query={query} />
    {ticket && !query.error && <><PageHeading title={ticket.title} note={`TICKET #${ticket.ticket_id}`}><Button disabled={!!action || query.isFetching} onClick={() => { setNotice(""); void query.refetch(); }}>Refresh ticket</Button></PageHeading>
      {notice && <p role="status" className="success-message">{notice}</p>}
      <div className="ticket-overview"><Status value={ticket.display_status} /><span>{label(ticket.category)}</span><span>{label(ticket.priority)} priority</span>
        {!vendor && <span>Assignee: {ticket.assignee?.display_name ?? "Unassigned"}</span>}</div>
      <div className="ticket-grid"><div className="ticket-main"><section className="panel"><div className="panel-heading"><h2>{vendor ? "Vendor request" : "Issue description"}</h2></div><div className="panel-body pre-wrap">
        {vendor ? ticket.vendor_request?.vendor_message ?? "No vendor message available." : ticket.description ?? "No description available."}
      </div></section>
        {ticket.resolution && !vendor && <section className="panel"><div className="panel-heading"><h2>Resolution</h2></div><div className="panel-body"><p className="pre-wrap">{ticket.resolution.summary}</p><p>{ticket.resolution.type && label(ticket.resolution.type)}</p><p>Reopen / close deadline: {date(ticket.resolution.auto_close_at)}</p></div></section>}
        {ticket.pending_user && !vendor && <p className="warning-note">{label(ticket.pending_user.reason)} · Respond before {date(ticket.pending_user.deadline)}. Use the available action, not an ordinary comment.</p>}
        {ticket.closure && !vendor && <p className="warning-note">Closed: {date(ticket.closure.closed_at)} · {label(ticket.closure.type)}. This ticket is read-only.</p>}
        {ticket.vendor_request && !vendor && user?.role !== "USER" && <section className="panel"><div className="panel-heading"><h2>Vendor collaboration</h2></div><div className="panel-body"><strong>{ticket.vendor_request.vendor_org.name}</strong><p>{label(ticket.vendor_request.status)}</p><p className="pre-wrap">{ticket.vendor_request.vendor_message}</p></div></section>}
        {action === "EDIT" && <TicketForm key={ticket.ticket_id} ticket={ticket} onDone={() => reload()} />}
        {action && actionLabels[action] && <WorkflowPanel key={`${id}-${action}`} ticket={ticket} action={action} onDone={reload} onCancel={() => setAction(null)} />}
        {!action && <><nav className="tab-bar" aria-label="Ticket sections">{(vendor ? ["attachments", "activity"] : ["comments", "attachments", "activity"]).map((value) => <Button key={value} type={(vendor && tab === "comments" ? "attachments" : tab) === value ? "primary" : "default"} onClick={() => setTab(value)}>{label(value)}</Button>)}</nav>
          {!vendor && tab === "comments" && <CommentsPanel key={id} ticket={ticket} onChange={() => reload()} />}
          {(tab === "attachments" || (vendor && tab === "comments")) && <AttachmentsPanel key={id} ticket={ticket} onChange={() => reload()} />}
          {tab === "activity" && <EventsPanel key={id} id={id} />}</>}
      </div><aside className="ticket-aside"><section className="panel"><div className="panel-heading"><h2>Available actions</h2></div><div className="panel-body action-list">
        {ticket.available_actions.filter((a) => a === "EDIT" || actionLabels[a]).map((a) => <Button key={a} disabled={!!action} onClick={() => { setNotice(""); setAction(a); }}>{a === "EDIT" ? "Edit ticket" : actionLabels[a]}</Button>)}
        {!ticket.available_actions.some((a) => a === "EDIT" || actionLabels[a]) && <p>No workflow action available.</p>}
      </div></section>
      {!vendor && <section className="panel"><div className="panel-heading"><h2>Service level</h2></div><dl className="account-facts"><div><dt>SLA</dt><dd>{ticket.sla ? <Status value={ticket.sla.status} /> : "Not available"}</dd></div><div><dt>Cycle / deadline</dt><dd>{ticket.sla?.cycle_no ?? "—"} / {date(ticket.sla?.deadline)}</dd></div><div><dt>Requester</dt><dd>{ticket.requester?.display_name ?? "Not available"}</dd></div><div><dt>Created</dt><dd>{date(ticket.created_at)}</dd></div></dl></section>}
      {vendor && ticket.vendor_request && <section className="panel"><div className="panel-body"><h2>Request status</h2><Status value={ticket.vendor_request.status} /><p>Requested {date(ticket.vendor_request.created_at)}</p><p>Responded {date(ticket.vendor_request.responded_at)}</p></div></section>}
      </aside></div></>}
  </>;
}
