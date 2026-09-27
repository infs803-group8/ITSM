import { LogoutOutlined, UserOutlined, UnorderedListOutlined, DashboardOutlined, ClockCircleOutlined } from "@ant-design/icons";
import { Button } from "antd";
import type { PropsWithChildren } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { shouldEnableMocks } from "../../api/config";
import { useAuth } from "../../features/auth/AuthProvider";
import { roleLabels } from "../../features/auth/roleLabels";
import { Brand } from "./Brand";

export function AppLayout({ children }: PropsWithChildren) {
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const staff = user && ["ENGINEER_TIER1", "ENGINEER_TIER2", "SERVICE_DESK_MANAGER"].includes(user.role);
  const title = pathname.startsWith("/tickets") ? "Tickets" : pathname === "/dashboard" ? "Service overview" : pathname === "/overdue" ? "SLA breaches" : "My profile";
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="app-sidebar">
      <Brand />
      <nav aria-label="Workspace navigation"><p className="nav-label">WORKSPACE</p>
        <NavLink to="/tickets"><UnorderedListOutlined aria-hidden="true" /><span>{user?.role === "EXTERNAL_VENDOR" ? "Vendor requests" : "Tickets"}</span></NavLink>
        {staff && <><NavLink to="/dashboard"><DashboardOutlined aria-hidden="true" /><span>Service overview</span></NavLink><NavLink to="/overdue"><ClockCircleOutlined aria-hidden="true" /><span>SLA breaches</span></NavLink></>}
        <NavLink to="/profile"><UserOutlined aria-hidden="true" /><span>My profile</span></NavLink>
      </nav>
      <div className="sidebar-footer"><span className="avatar small">{user?.display_name.slice(0, 1).toUpperCase()}</span>
        <div><strong>{user?.display_name}</strong><small>{user && roleLabels[user.role]}</small></div>
      </div>
    </aside>
    <div className="workspace">
      <header className="workspace-header"><span><span className="breadcrumb-parent">Workspace / </span>{title}</span>
        <div className="header-actions">{shouldEnableMocks(import.meta.env) && <span className="mode-badge">LOCAL MOCK</span>}
          <Button icon={<LogoutOutlined aria-hidden="true" />} onClick={signOut}>Sign out</Button>
        </div>
      </header>
      <main id="main-content" className="workspace-content">{children}</main>
      <footer className="workspace-footer">IT SERVICE DESK <span>SERVICE OPERATIONS</span></footer>
    </div>
  </div>;
}
