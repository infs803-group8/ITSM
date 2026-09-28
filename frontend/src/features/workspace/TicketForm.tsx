import { useState, type FormEvent } from "react";
import { Button } from "antd";
import { Link, useNavigate } from "react-router-dom";
import { api15CreateTicket, api18UpdateTicket } from "../../api/generated/sdk.gen";
import type { TicketCreateRequest, TicketDetail, TicketUpdateRequest } from "../../api/types";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";
import { label, PageHeading, QueryNotice, useReference, useWrite } from "./shared";

export function TicketForm({ ticket, onDone }: { ticket?: TicketDetail; onDone?: () => void }) {
  const reference = useReference(); const write = useWrite(ticket?.ticket_id); const navigate = useNavigate();
  const [validation, setValidation] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const values = new FormData(event.currentTarget);
    const body: TicketCreateRequest = { title: String(values.get("title")).trim(), description: String(values.get("description")).trim(),
      category: values.get("category") as TicketCreateRequest["category"], priority: values.get("priority") as TicketCreateRequest["priority"] };
    if (!body.title || !body.description) { setValidation("Enter a title and description, not only spaces."); return; }
    setValidation("");
    const changed: TicketUpdateRequest = {};
    if (ticket) {
      for (const field of ["title", "description", "category", "priority"] as const) {
        if (body[field] !== ticket[field]) Object.assign(changed, { [field]: body[field] });
      }
      if (!Object.keys(changed).length) { onDone?.(); return; }
    }
    await write.run(async (signal) => ticket
      ? (await api18UpdateTicket({ path: { id: ticket.ticket_id }, body: changed, signal })).data.data
      : (await api15CreateTicket({ body, signal })).data.data,
    (result) => { if (ticket) onDone?.(); else navigate(`/tickets/${result.ticket_id}`, { replace: true }); });
  }
  return <section className="panel"><div className="panel-heading"><h2>{ticket ? "Edit ticket" : "Issue information"}</h2><p>Do not include passwords or other credentials.</p></div>
    <div className="panel-body"><QueryNotice query={reference} />{write.error != null && <ApiErrorNotice error={write.error} />}{validation && <p role="alert">{validation}</p>}
      <form onSubmit={submit} className="work-form"><fieldset disabled={write.busy || !reference.data}><label>Title<input name="title" required maxLength={200} defaultValue={ticket?.title} /></label>
        <label>Description<textarea name="description" required maxLength={5000} rows={6} defaultValue={ticket?.description ?? ""} /></label>
        <div className="form-columns"><label>Category<select aria-label="Category" name="category" required defaultValue={ticket?.category ?? ""}><option value="" disabled>Select category</option>{reference.data?.categories.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label>
          <label>Priority<select aria-label="Priority" name="priority" required defaultValue={ticket?.priority ?? "MEDIUM"}>{reference.data?.priorities.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label></div>
        <div className="form-actions"><Button htmlType="submit" type="primary" loading={write.busy}>{ticket ? "Save ticket" : "Submit ticket"}</Button>{ticket ? <Button onClick={onDone}>Cancel edit</Button> : <Link to="/tickets">Cancel</Link>}</div>
      </fieldset></form></div></section>;
}
export function CreateTicketPage() { return <><PageHeading title="Create ticket" note="Report an IT issue. Assignment and SLA are managed by the service." /><TicketForm /></>; }
