import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Progress } from "antd";
import { api02CreateAttachmentUpload, api03CompleteAttachmentUpload, api04ListAttachments, api05GetAttachmentDownload } from "../../api/generated/sdk.gen";
import type { AttachmentVisibility, PresignData, PresignRequest, TicketDetail } from "../../api/types";
import { putAttachment, safeTransferUrl, validateAttachment } from "../../api/attachmentTransfer";
import { ApiErrorNotice } from "../../components/ApiErrorNotice";
import { date, label, Pager, QueryNotice, useReference, useWorkspaceKey, useWrite } from "./shared";

export function AttachmentsPanel({ ticket, onChange }: { ticket: TicketDetail; onChange: () => void }) {
  const key = useWorkspaceKey(); const reference = useReference(); const write = useWrite(); const download = useWrite();
  const [page, setPage] = useState(1); const [file, setFile] = useState<File | null>(null); const [validation, setValidation] = useState("");
  const [progress, setProgress] = useState(0); const [uploaded, setUploaded] = useState<PresignData | null>(null); const [success, setSuccess] = useState("");
  const query = useQuery({ queryKey: [...key, "ticket", ticket.ticket_id, "attachments", page], queryFn: async ({ signal }) => (await api04ListAttachments({ path: { id: ticket.ticket_id }, query: { page, page_size: 20 }, signal })).data });
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!file || !reference.data) return;
    const problem = validateAttachment(file, reference.data.attachment); if (problem) { setValidation(problem); return; }
    if (uploaded && Date.parse(uploaded.expires_at) <= Date.now()) { setValidation("This upload session expired. Start a new upload."); return; }
    const visibility = new FormData(event.currentTarget).get("visibility") as AttachmentVisibility;
    setValidation(""); setSuccess("");
    await write.run(async (signal) => {
      let session = uploaded;
      if (!session) {
        session = (await api02CreateAttachmentUpload({ path: { id: ticket.ticket_id }, body: { file_name: file.name, content_type: file.type as PresignRequest["content_type"], size_bytes: file.size, visibility }, signal })).data.data;
        await putAttachment(file, session, signal, setProgress); signal.throwIfAborted(); setUploaded(session);
      }
      return api03CompleteAttachmentUpload({ path: { id: ticket.ticket_id }, body: { upload_id: session.upload_id }, signal });
    }, () => { setUploaded(null); setFile(null); setProgress(0); setSuccess("Attachment confirmed and added to this ticket."); void query.refetch(); onChange(); });
  }
  return <section className="panel"><div className="panel-heading"><h2>Attachments</h2><p>Maximum 10 MiB · private storage. Allowed formats: {reference.data?.attachment.allowed_types.map((rule) => rule.extension).join(", ") ?? "loading"}.</p></div><div className="panel-body"><QueryNotice query={query} />
    {download.error != null && <ApiErrorNotice error={download.error} />}
    {query.data && !query.error && <>{query.data.data.map((a) => <div className="attachment-row" key={a.attachment_id}><div><strong>{a.file_name}</strong><small>{Math.ceil(a.size_bytes / 1024)} KiB · {label(a.visibility)} · {date(a.created_at)}</small></div>
      <Button disabled={download.busy} onClick={() => void download.run((signal) => api05GetAttachmentDownload({ path: { id: ticket.ticket_id, attachment_id: a.attachment_id }, signal }), (r) => {
        const anchor = document.createElement("a"); anchor.href = safeTransferUrl(r.data.data.download_url); anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; anchor.referrerPolicy = "no-referrer"; anchor.click();
      })}>Download {a.file_name}</Button></div>)}{!query.data.data.length && <p>No attachments yet.</p>}<Pager page={page} total={query.data.meta.total_pages} onChange={setPage} /></>}
    {success && <p role="status">{success}</p>}
    {ticket.available_actions.includes("UPLOAD_ATTACHMENT") && <form className="work-form" onSubmit={submit}><QueryNotice query={reference} />{write.error != null && <ApiErrorNotice error={write.error} />}{validation && <p role="alert">{validation}</p>}
      <fieldset disabled={write.busy || !reference.data}><label>Attachment file<input key={success} type="file" disabled={!!uploaded} accept={reference.data?.attachment.allowed_types.map((rule) => `.${rule.extension.replace(/^\./, "")}`).join(",")} onChange={(e) => { setFile(e.target.files?.[0] ?? null); setValidation(""); setSuccess(""); }} /></label>
        <label>Attachment visibility<select name="visibility" disabled={!!uploaded}>{reference.data?.attachment_visibilities.filter((v) => v !== "VENDOR_SHARED" || ticket.vendor_request?.status === "ACTIVE").map((v) => <option key={v} value={v}>{label(v)}</option>)}</select></label>
        {write.busy && <Progress percent={progress} />}
        {uploaded && <p>File transfer finished. Confirmation is still required; retrying will not upload the file again.</p>}
        <div className="form-actions"><Button htmlType="submit" type="primary" loading={write.busy} disabled={!file}>{uploaded ? "Retry confirmation" : "Upload attachment"}</Button>
          {uploaded && <Button onClick={() => { setUploaded(null); setProgress(0); write.clearError(); }}>Start a new upload</Button>}</div>
      </fieldset></form>}
  </div></section>;
}
