import { Link, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "../components/layout/AppLayout";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { PublicRoute, RoleRoute } from "./roleRoutes";
import { TicketListPage } from "../features/workspace/TicketListPage";
import { CreateTicketPage } from "../features/workspace/TicketForm";
import { TicketDetailPage } from "../features/workspace/TicketDetailPage";
import { DashboardPage, OverduePage } from "../features/workspace/DashboardPage";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/profile" replace />} />
      <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
      <Route path="/profile" element={<RoleRoute><AppLayout><ProfilePage /></AppLayout></RoleRoute>} />
      <Route path="/tickets" element={<RoleRoute><AppLayout><TicketListPage /></AppLayout></RoleRoute>} />
      <Route path="/tickets/new" element={<RoleRoute roles={["USER"]}><AppLayout><CreateTicketPage /></AppLayout></RoleRoute>} />
      <Route path="/tickets/:id" element={<RoleRoute><AppLayout><TicketDetailPage /></AppLayout></RoleRoute>} />
      <Route path="/dashboard" element={<RoleRoute roles={["ENGINEER_TIER1", "ENGINEER_TIER2", "SERVICE_DESK_MANAGER"]}><AppLayout><DashboardPage /></AppLayout></RoleRoute>} />
      <Route path="/overdue" element={<RoleRoute roles={["ENGINEER_TIER1", "ENGINEER_TIER2", "SERVICE_DESK_MANAGER"]}><AppLayout><OverduePage /></AppLayout></RoleRoute>} />
      <Route path="/forbidden" element={<RoleRoute><main className="route-message"><p className="eyebrow">403 / ACCESS RESTRICTED</p>
        <h1>This page is not available to your role</h1><Link to="/profile">Return to my profile</Link></main></RoleRoute>} />
      <Route path="*" element={<main className="route-message"><p className="eyebrow">404 / PAGE NOT FOUND</p>
        <h1>We could not find that page</h1><Link to="/">Return to workspace</Link></main>} />
    </Routes>
  );
}
