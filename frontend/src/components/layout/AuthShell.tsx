import { ArrowUpOutlined } from "@ant-design/icons";
import type { PropsWithChildren } from "react";
import { Brand } from "./Brand";

export function AuthShell({ children }: PropsWithChildren) {
  return <div className="auth-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="auth-rail">
      <Brand />
      <div className="rail-content">
        <p className="eyebrow">ONE PLACE FOR IT SUPPORT</p>
        <h2>IT support.<br />In one place.</h2>
        <p className="rail-description">Report an issue, stay informed and get the help you need.</p>
        <ol className="support-steps">
          {["Report an issue", "Follow its progress", "Get back to work"].map((step, index) =>
            <li key={step}><span>0{index + 1}</span><strong>{step}</strong><ArrowUpOutlined rotate={45} aria-hidden="true" /></li>)}
        </ol>
      </div>
      <div className="rail-footer"><span>IT SERVICE MANAGEMENT</span><span>GROUP 08</span></div>
    </aside>
    <div className="auth-main">
      <header className="auth-topline"><span>ITSM / ACCOUNT ACCESS</span><span className="portal-label">SERVICE DESK PORTAL</span></header>
      <main id="main-content" className="auth-form-area"><div className="auth-card">{children}</div></main>
      <footer className="auth-footer">Account access is managed by your service desk.</footer>
    </div>
  </div>;
}
