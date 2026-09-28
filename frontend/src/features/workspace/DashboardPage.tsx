import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "antd";
import { Link } from "react-router-dom";
import { api06DashboardSummary, api07OverdueTickets } from "../../api/generated/sdk.gen";
import type { Api07OverdueTicketsData } from "../../api/types";
import { date, label, PageHeading, Pager, QueryNotice, Status, useReference, useWorkspaceKey } from "./shared";

export function DashboardPage() {
  const key = useWorkspaceKey(); const query = useQuery({ queryKey: [...key, "dashboard"], queryFn: async ({ signal }) => (await api06DashboardSummary({ signal })).data.data });
  return <><PageHeading title="Service overview" note="Current work, service levels and items requiring attention."><Button disabled={query.isFetching} onClick={() => void query.refetch()}>Refresh overview</Button></PageHeading>
    <QueryNotice query={query} />{query.data && !query.error && <><p className="snapshot">Scope: {label(query.data.scope)} · Updated {date(query.data.generated_at)}</p>
      <div className="metric-grid"><div className="metric"><span>Active tickets</span><strong>{query.data.counts.total_active}</strong></div><div className="metric at-risk"><span>SLA at risk</span><strong>{query.data.sla.at_risk}</strong></div>
        <Link className="metric overdue" to="/overdue"><span>Current overdue</span><strong>{query.data.sla.overdue}</strong><small>Open overdue queue →</small></Link><div className="metric"><span>Reopened / unassigned</span><strong>{query.data.action_required.reopened_unassigned}</strong></div></div>
      <section className="panel"><div className="panel-heading"><h2>Ticket lifecycle</h2><p>SLA state is separate from lifecycle status.</p></div><div className="lifecycle-grid">{Object.entries(query.data.counts).filter(([name]) => name !== "total_active").map(([name, count]) => <div key={name}><Status value={name} /><strong>{count}</strong></div>)}</div></section>
      <div className="form-actions"><Link className="primary-link" to="/tickets">Open ticket queue</Link><Link className="secondary-link" to="/overdue">Current and historical SLA breaches</Link></div></>}
  </>;
}
export function OverduePage() {
  const key = useWorkspaceKey(); const reference = useReference();
  const [filters, setFilters] = useState<NonNullable<Api07OverdueTicketsData["query"]>>({ mode: "current", page: 1, page_size: 20 });
  const query = useQuery({ queryKey: [...key, "overdue", filters], queryFn: async ({ signal }) => (await api07OverdueTickets({ signal, query: filters })).data });
  return <><PageHeading title="SLA breaches" note="Current shows active overdue cycles. History preserves past breaches, even after resolution." /><QueryNotice query={reference} />
    <div className="filter-bar"><label>View<select aria-label="View" value={filters.mode} onChange={(e) => setFilters({ ...filters, mode: e.target.value as "current" | "history", page: 1 })}><option value="current">Current</option><option value="history">History</option></select></label>
      <label>Category<select value={filters.category ?? ""} onChange={(e) => setFilters({ ...filters, category: (e.target.value || undefined) as typeof filters.category, page: 1 })}><option value="">All categories</option>{reference.data?.categories.map((v) => <option key={v}>{v}</option>)}</select></label>
      <label>Priority<select value={filters.priority ?? ""} onChange={(e) => setFilters({ ...filters, priority: (e.target.value || undefined) as typeof filters.priority, page: 1 })}><option value="">All priorities</option>{reference.data?.priorities.map((v) => <option key={v}>{v}</option>)}</select></label></div>
    <QueryNotice query={query} />{query.data && !query.error && <section className="panel table-panel"><table className="data-table"><thead><tr><th>Ticket</th><th>Status</th><th>Assignee</th><th>Cycle</th><th>Deadline / breach</th><th>Current?</th></tr></thead><tbody>{query.data.data.map((t, index) => <tr key={`${t.ticket_id}-${t.sla_cycle_no}-${index}`}><td><Link to={`/tickets/${t.ticket_id}`}>#{t.ticket_id} {t.title}</Link></td><td><Status value={t.display_status} /></td><td>{t.assignee?.display_name ?? "Unassigned"}</td><td>{t.sla_cycle_no}</td><td>{date(t.sla_deadline)}<small>{date(t.overdue_at)}</small></td><td>{t.is_current ? "Yes" : "Historical"}</td></tr>)}</tbody></table>
      {!query.data.data.length && <p className="empty-state">No SLA breaches in this view.</p>}<Pager page={filters.page ?? 1} total={query.data.meta.total_pages} onChange={(page) => setFilters({ ...filters, page })} /></section>}
  </>;
}
