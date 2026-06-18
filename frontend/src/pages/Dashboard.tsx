import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api, type Campaign, type Contact, type List } from "../lib/api";
import { Card, ErrorBanner, PageHeader, Spinner, errMessage } from "../components/ui";

export default function Dashboard() {
  const { me } = useAuth();
  const [counts, setCounts] = useState<{
    campaigns: number;
    contacts: number;
    lists: number;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [campaigns, contacts, lists] = await Promise.all([
          api.get<Campaign[]>("/api/campaigns"),
          api.get<Contact[]>("/api/contacts"),
          api.get<List[]>("/api/lists"),
        ]);
        setCounts({
          campaigns: campaigns.length,
          contacts: contacts.length,
          lists: lists.length,
        });
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div>
      <PageHeader
        title={`Welcome${me?.user.name ? ", " + me.user.name : ""}`}
        subtitle={`You are working in ${me?.workspace.name}.`}
      />

      <ErrorBanner message={error} />

      {loading ? (
        <Spinner label="Loading overview…" />
      ) : (
        <div className="stat-grid">
          <Link to="/campaigns" className="stat-card">
            <span className="stat-label">Campaigns</span>
            <span className="stat-value">{counts?.campaigns ?? 0}</span>
          </Link>
          <Link to="/contacts" className="stat-card">
            <span className="stat-label">Contacts</span>
            <span className="stat-value">{counts?.contacts ?? 0}</span>
          </Link>
          <Link to="/lists" className="stat-card">
            <span className="stat-label">Lists</span>
            <span className="stat-value">{counts?.lists ?? 0}</span>
          </Link>
        </div>
      )}

      <Card title="Quick start">
        <ol className="checklist">
          <li>
            <Link to="/contacts">Import your contacts</Link> from a CSV or add them
            manually.
          </li>
          <li>
            Organize them into <Link to="/lists">lists</Link> or build dynamic{" "}
            <Link to="/segments">segments</Link>.
          </li>
          <li>
            Verify a <Link to="/settings">sending domain</Link> for the best
            deliverability.
          </li>
          <li>
            Compose and send your first <Link to="/campaigns">campaign</Link>.
          </li>
        </ol>
      </Card>
    </div>
  );
}
