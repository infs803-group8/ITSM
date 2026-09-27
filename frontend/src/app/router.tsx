import { Link, Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "../components/layout/AppLayout";
import { LoginPage } from "../features/auth/LoginPage";
import { RegisterPage } from "../features/auth/RegisterPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { PublicRoute, RoleRoute } from "./roleRoutes";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/profile" replace />} />
      <Route path="/login" element={<PublicRoute><LoginPage /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><RegisterPage /></PublicRoute>} />
      <Route path="/profile" element={<RoleRoute><AppLayout><ProfilePage /></AppLayout></RoleRoute>} />
      <Route path="/forbidden" element={<RoleRoute><main className="route-message"><p className="eyebrow">403 / ACCESS RESTRICTED</p>
        <h1>This page is not available to your role</h1><Link to="/profile">Return to my profile</Link></main></RoleRoute>} />
      <Route path="*" element={<main className="route-message"><p className="eyebrow">404 / PAGE NOT FOUND</p>
        <h1>We could not find that page</h1><Link to="/">Return to workspace</Link></main>} />
    </Routes>
  );
}
