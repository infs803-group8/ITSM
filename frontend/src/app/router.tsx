import { Navigate, Route, Routes } from "react-router-dom";

export function AppRouter() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <main className="shell">
            <h1>IT Service Desk</h1>
            <p>The frontend scaffold is ready. Implement screens from the approved backlog.</p>
          </main>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
