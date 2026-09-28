import { useQuery } from "@tanstack/react-query";
import { api33ListVendorRequestHistory } from "../../api/generated/sdk.gen";
import { date, QueryNotice, Status, useWorkspaceKey } from "./shared";

export function VendorHistoryPanel({ ticketId }: { ticketId: number }) {
  const key = useWorkspaceKey();
  const query = useQuery({
    queryKey: [...key, "ticket", ticketId, "vendor-history"],
    queryFn: async ({ signal }) => (await api33ListVendorRequestHistory({ path: { id: ticketId }, signal })).data.data,
  });

  return <section className="panel"><div className="panel-heading"><h2>Vendor request history</h2>
    <p>Persisted requests and replies visible to your role and vendor organisation.</p></div>
    <div className="panel-body"><QueryNotice query={query} />
      {query.data && !query.error && <div className="vendor-history-list">
        {query.data.map((item) => <article className="vendor-history-entry" key={item.vendor_request_id}>
          <div className="vendor-history-heading"><div><strong>{item.vendor_org.name}</strong>
            <small>Request #{item.vendor_request_id} · sent {date(item.created_at)}</small></div><Status value={item.status} /></div>
          <div className="vendor-message"><h3>Request to vendor</h3><p className="pre-wrap">{item.vendor_message}</p></div>
          {item.response ? <div className="vendor-message vendor-response"><h3>Response from vendor</h3>
            <p className="pre-wrap">{item.response.message}</p><small>Received {date(item.response.created_at)}</small></div>
            : <p className="vendor-response-empty">{item.status === "ACTIVE" ? "Awaiting a vendor response." : "No vendor response was recorded."}</p>}
        </article>)}
        {!query.data.length && <p>No vendor requests have been recorded for this ticket.</p>}
      </div>}
    </div>
  </section>;
}
