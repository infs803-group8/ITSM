import { Button } from "antd";
import { mockCredentials } from "../../mocks/state";
import type { LoginRequest } from "../../api/types";

export default function DevDemoAccount({ onFill }: { onFill: (values: LoginRequest) => void }) {
  return <aside className="mock-notice" aria-label="Local demo account">
    <div><strong>LOCAL MOCK MODE</strong><p>No live backend. Demo changes reset on reload.</p></div>
    <Button size="small" onClick={() => onFill(mockCredentials)}>Use demo account</Button>
  </aside>;
}
