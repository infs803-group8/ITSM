import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { Button } from "antd";
import { api16ListTickets } from "../../api/generated/sdk.gen";
import type { Api16ListTicketsData } from "../../api/types";
import { useAuth } from "../auth/AuthProvider";
import { date, label, PageHeading, Pager, QueryNotice, Status, useReference, useWorkspaceKey } from "./shared";

export function TicketListPage() {
  const { user } = useAuth(); const location = useLocation(); const key = useWorkspaceKey();
  const reference = useReference();
  const [filters, setFilters] = useState<NonNullable<Api16ListTicketsData["query"]>>({ page: 1, page_size: 20, sort_by: "updated_at", sort_order: "desc" });
  const query = useQuery({ queryKey: [...key, "tickets", filters], queryFn: async ({ signal }) => (await api16ListTickets({ query: filters, signal })).data });
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = new FormData(event.currentTarget);
    setFilters({ page: 1, page_size: 20, search: String(values.get("search") || "") || undefined,
      status: (values.get("status") || undefined) as typeof filters.status,
      category: (values.get("category") || undefined) as typeof filters.category,
      priority: (values.get("priority") || undefined) as typeof filters.priority,
      sla_status: (values.get("sla_status") || undefined) as typeof filters.sla_status,
      assignee_id: values.get("assignee_id") ? Number(values.get("assignee_id")) : undefined,
      sort_by: values.get("sort_by") as typeof filters.sort_by, sort_order: values.get("sort_order") as typeof filters.sort_order });
  }
  return <><PageHeading title={user?.role === "EXTERNAL_VENDOR" ? "Vendor requests" : "Tickets"} note="Your authorised work queue. Filters and counts are supplied by the service.">
    {user?.role === "USER" && <Link className="primary-link" to="/tickets/new">Create ticket</Link>}</PageHeading>
    {location.state?.notice && <p className="success-message" role="status">{String(location.state.notice)}</p>}
    <QueryNotice query={reference} />
    <form className="filter-bar" onSubmit={apply}>
      <label>Search<input name="search" maxLength={200} placeholder="Ticket title" /></label>
      <label>Status<select name="status"><option value="">All statuses</option>{reference.data?.ticket_statuses.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label>
      <label>Category<select name="category"><option value="">All categories</option>{reference.data?.categories.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label>
      <label>Priority<select name="priority"><option value="">All priorities</option>{reference.data?.priorities.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label>
      {user?.role !== "EXTERNAL_VENDOR" && <label>SLA<select name="sla_status"><option value="">All SLA states</option>{["ON_TRACK", "AT_RISK", "OVERDUE", "PAUSED", "MET"].map((v) => <option key={v}>{v}</option>)}</select></label>}
      {user?.role === "SERVICE_DESK_MANAGER" && <label>Assignee ID<input name="assignee_id" type="number" min="1" step="1" /></label>}
      <label>Sort by<select name="sort_by" defaultValue="updated_at"><option value="updated_at">Updated</option><option value="created_at">Created</option><option value="priority">Priority</option>{user?.role !== "EXTERNAL_VENDOR" && <option value="sla_deadline">SLA deadline</option>}</select></label>
      <label>Order<select name="sort_order" defaultValue="desc"><option value="desc">Descending</option><option value="asc">Ascending</option></select></label>
      <Button htmlType="submit" type="primary">Apply filters</Button>
    </form>
    <QueryNotice query={query} />
    {query.data && !query.error && <section className="panel table-panel"><div className="panel-heading"><h2>{query.data.meta.total} tickets</h2></div>
      <table className="data-table"><thead><tr><th>Ticket</th><th>Category</th><th>Priority</th><th>Status</th>{user?.role !== "EXTERNAL_VENDOR" && <><th>Assignee / SLA</th><th>Updated</th></>}</tr></thead>
        <tbody>{query.data.data.map((ticket) => <tr key={ticket.ticket_id}><td><Link to={`/tickets/${ticket.ticket_id}`}><small>#{ticket.ticket_id}</small><strong>{ticket.title}</strong></Link></td>
          <td>{label(ticket.category)}</td><td>{label(ticket.priority)}</td><td><Status value={ticket.display_status} /></td>
          {user?.role !== "EXTERNAL_VENDOR" && <><td>{ticket.assignee?.display_name ?? "Unassigned"}{ticket.sla && <><br /><Status value={ticket.sla.status} /><small>{date(ticket.sla.deadline)}</small></>}</td><td>{date(ticket.updated_at)}</td></>}</tr>)}</tbody></table>
      {!query.data.data.length && <p className="empty-state">No tickets match these filters.</p>}
      <Pager page={filters.page ?? 1} total={query.data.meta.total_pages} onChange={(page) => setFilters({ ...filters, page })} /></section>}
  </>;
}
