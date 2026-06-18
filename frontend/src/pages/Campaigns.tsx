import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Campaign } from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  Spinner,
  StatusPill,
  errMessage,
} from "../components/ui";

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const c = await api.get<Campaign[]>("/api/campaigns");
        setCampaigns(c);
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
        title="Campaigns"
        subtitle="Compose, send, and measure your emails."
        actions={
          <Link to="/campaigns/new" className="btn btn-primary">
            New campaign
          </Link>
        }
      />
      <ErrorBanner message={error} />

      <Card>
        {loading ? (
          <Spinner label="Loading campaigns…" />
        ) : campaigns.length === 0 ? (
          <Empty message="No campaigns yet. Create your first one." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>From</th>
                  <th>Variants</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                    </td>
                    <td className="muted">
                      {c.from_name}
                      {c.from_email ? ` <${c.from_email}>` : ""}
                    </td>
                    <td className="num">{c.variants?.length ?? 0}</td>
                    <td>
                      <StatusPill status={c.status} />
                    </td>
                    <td className="row-actions">
                      <Link
                        to={`/campaigns/${c.id}/analytics`}
                        className="btn btn-ghost btn-sm"
                      >
                        Analytics
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
