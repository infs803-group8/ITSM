import { Button } from "antd";
import { mockCredentials, demoRoles } from "../../mocks/state";
import { useState } from "react";
import { roleLabels } from "./roleLabels";
import type { LoginRequest } from "../../api/types";

export default function DevDemoAccount({ onFill }: { onFill: (values: LoginRequest) => void }) {
  const [email, setEmail] = useState(mockCredentials.email);
  return <aside className="mock-notice" aria-label="Local demo account">
    <div><strong>LOCAL MOCK MODE</strong><p>No live backend. Demo changes reset on reload.</p></div>
    <label>Demo role <select aria-label="Demo role" value={email} onChange={(e) => setEmail(e.target.value)}><option value={mockCredentials.email}>Requester</option>{demoRoles.map((actor) => <option key={actor.email} value={actor.email}>{roleLabels[actor.role]}</option>)}</select></label>
    <Button size="small" onClick={() => onFill({ ...mockCredentials, email })}>Use demo account</Button>
  </aside>;
}
