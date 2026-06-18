import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Spinner } from "./ui";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();

  if (loading) {
    return (
      <div className="full-center">
        <Spinner label="Loading…" />
      </div>
    );
  }

  if (!me) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
