import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "antd";
import { api19ListComments, api20CreateComment } from "../../api/generated/sdk.gen";
import type { CommentVisibility, TicketDetail } from "../../api/types";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";
import { date, label, Pager, QueryNotice, useReference, useWorkspaceKey, useWrite } from "./shared";

export function CommentsPanel({ ticket, onChange }: { ticket: TicketDetail; onChange: () => void }) {
  const key = useWorkspaceKey(); const write = useWrite(ticket.ticket_id); const reference = useReference(); const [page, setPage] = useState(1);
  const [message, setMessage] = useState(""); const [validation, setValidation] = useState("");
  const query = useQuery({ queryKey: [...key, "ticket", ticket.ticket_id, "comments", page], queryFn: async ({ signal }) => (await api19ListComments({ path: { id: ticket.ticket_id }, query: { page, page_size: 20 }, signal })).data });
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!message.trim()) { setValidation("Enter a comment, not only spaces."); return; }
    const visibility = new FormData(event.currentTarget).get("visibility") as CommentVisibility;
    setValidation(""); await write.run((signal) => api20CreateComment({ path: { id: ticket.ticket_id }, body: { message: message.trim(), visibility }, signal }),
      () => { setMessage(""); void query.refetch(); onChange(); });
  }
  return <section className="panel"><div className="panel-heading"><h2>Comments</h2><p>Comments do not confirm a resolution or resume a waiting ticket. Use the action above.</p></div><div className="panel-body">
    <QueryNotice query={query} />{query.data && !query.error && <>{query.data.data.map((c) => <article className="thread-entry" key={c.comment_id}><strong>{c.author.display_name}</strong><small>{label(c.visibility)} · {date(c.created_at)}</small><p className="pre-wrap">{c.message}</p></article>)}
      {!query.data.data.length && <p>No comments yet.</p>}<Pager page={page} total={query.data.meta.total_pages} onChange={setPage} /></>}
    {ticket.available_actions.includes("COMMENT") && <form onSubmit={submit} className="work-form"><QueryNotice query={reference} />
      {write.error != null && <ApiErrorNotice error={write.error} />}{validation && <p role="alert">{validation}</p>}
      <fieldset disabled={write.busy || !reference.data}><label>Comment<textarea value={message} onChange={(e) => setMessage(e.target.value)} required maxLength={4000} rows={3} /></label>
        <label>Comment visibility<select name="visibility">{reference.data?.comment_visibilities.map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label>
        <Button htmlType="submit" type="primary" loading={write.busy}>Add comment</Button></fieldset></form>}
  </div></section>;
}
