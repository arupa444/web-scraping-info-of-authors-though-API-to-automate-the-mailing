import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import AppShell from "./components/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Contacts from "./pages/Contacts";
import Lists from "./pages/Lists";
import Segments from "./pages/Segments";
import Campaigns from "./pages/Campaigns";
import CampaignNew from "./pages/CampaignNew";
import CampaignAnalytics from "./pages/CampaignAnalytics";
import Templates from "./pages/Templates";
import TemplateBuilder from "./pages/TemplateBuilder";
import Automations from "./pages/Automations";
import AutomationBuilder from "./pages/AutomationBuilder";
import Forms from "./pages/Forms";
import Settings from "./pages/Settings";

export default function App() {
  const { me, loading } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={
          loading ? (
            <div className="full-center">
              <Spinner label="Loading…" />
            </div>
          ) : me ? (
            <Navigate to="/" replace />
          ) : (
            <Login />
          )
        }
      />

      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/contacts" element={<Contacts />} />
        <Route path="/lists" element={<Lists />} />
        <Route path="/segments" element={<Segments />} />
        <Route path="/campaigns" element={<Campaigns />} />
        <Route path="/campaigns/new" element={<CampaignNew />} />
        <Route path="/campaigns/:id/edit" element={<CampaignNew />} />
        <Route path="/campaigns/:id/analytics" element={<CampaignAnalytics />} />
        <Route path="/templates" element={<Templates />} />
        <Route path="/templates/new" element={<TemplateBuilder />} />
        <Route path="/templates/:id" element={<TemplateBuilder />} />
        <Route path="/automations" element={<Automations />} />
        <Route path="/automations/new" element={<AutomationBuilder />} />
        <Route path="/automations/:id" element={<AutomationBuilder />} />
        <Route path="/forms" element={<Forms />} />
        <Route path="/settings" element={<Settings />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
