import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  type Campaign,
  type CampaignAnalytics as Analytics,
} from "../lib/api";
import {
  Card,
  ErrorBanner,
  PageHeader,
  Spinner,
  errMessage,
} from "../components/ui";

interface Metric {
  key: keyof Analytics;
  label: string;
  phase4?: boolean;
  pct?: boolean;
}

const METRICS: Metric[] = [
  { key: "sent", label: "Sent" },
  { key: "delivered", label: "Delivered", phase4: true },
  { key: "unique_opens", label: "Unique opens" },
  { key: "total_opens", label: "Total opens" },
  { key: "unique_clicks", label: "Unique clicks" },
  { key: "total_clicks", label: "Total clicks" },
  { key: "ctr", label: "CTR", pct: true },
  { key: "ctor", label: "CTOR", pct: true },
  { key: "hard_bounce", label: "Hard bounces" },
  { key: "soft_bounce", label: "Soft bounces" },
  { key: "unsubscribes", label: "Unsubscribes" },
  { key: "complaints", label: "Complaints", phase4: true },
];

function fmt(m: Metric, v: number | null): string {
  if (v === null || v === undefined) return "—";
  if (m.pct) return `${(v * 100).toFixed(1)}%`;
  return String(v);
}

export default function CampaignAnalytics() {
  const { id } = useParams<{ id: string }>();
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [c, a] = await Promise.all([
          api.get<Campaign>(`/api/campaigns/${id}`),
          api.get<Analytics>(`/api/campaigns/${id}/analytics`),
        ]);
        setCampaign(c);
        setData(a);
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  return (
    <div>
      <PageHeader
        title={campaign ? campaign.name : "Campaign analytics"}
        subtitle="Engagement metrics for this campaign."
        actions={
          <Link to="/campaigns" className="btn btn-ghost">
            ← Back to campaigns
          </Link>
        }
      />
      <ErrorBanner message={error} />

      {loading ? (
        <Spinner label="Loading analytics…" />
      ) : data ? (
        <>
          <div className="metric-grid">
            {METRICS.map((m) => (
              <div className="metric-card" key={m.key}>
                <span className="metric-label">{m.label}</span>
                <span className="metric-value">{fmt(m, data[m.key])}</span>
                {m.phase4 ? (
                  <span className="metric-note">
                    available with ESP integration (Phase 4)
                  </span>
                ) : null}
              </div>
            ))}
          </div>
          <Card>
            <p className="muted small">
              Delivered and complaints are not tracked in Phase 1 and render as
              “—”. They become available once an ESP integration is connected
              (Phase 4).
            </p>
          </Card>
        </>
      ) : null}
    </div>
  );
}
