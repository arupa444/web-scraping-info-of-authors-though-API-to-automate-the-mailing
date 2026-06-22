import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  api,
  analyticsNarrative,
  getCampaignNarrative,
  getCampaignRecipients,
  getCampaignVariants,
  type AnalyticsNarrative,
  type Campaign,
  type CampaignAnalytics as Analytics,
  type CampaignRecipient,
  type CampaignVariants,
} from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  Spinner,
  errMessage,
} from "../components/ui";

const AI_DISABLED = "AI not configured";

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
  { key: "replies", label: "Replies" },
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
  const [variants, setVariants] = useState<CampaignVariants | null>(null);
  const [recipients, setRecipients] = useState<CampaignRecipient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // AI narrative
  const [narrative, setNarrative] = useState<AnalyticsNarrative | null>(null);
  const [narrativeBusy, setNarrativeBusy] = useState(false);
  const [narrativeError, setNarrativeError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [c, a, v, n, r] = await Promise.all([
          api.get<Campaign>(`/api/campaigns/${id}`),
          api.get<Analytics>(`/api/campaigns/${id}/analytics`),
          getCampaignVariants(id!).catch(() => null),
          getCampaignNarrative(id!).catch(() => null),
          getCampaignRecipients(id!).catch(() => []),
        ]);
        setCampaign(c);
        setData(a);
        setVariants(v);
        setRecipients(r);
        // Show a previously-generated AI summary so it survives refreshes.
        if (n && n.summary) setNarrative(n);
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  async function onGenerateNarrative() {
    if (!id) return;
    setNarrativeError(null);
    setNarrative(null);
    setNarrativeBusy(true);
    try {
      const res = await analyticsNarrative(id);
      setNarrative(res);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setNarrativeError(AI_DISABLED);
      } else {
        setNarrativeError(errMessage(err));
      }
    } finally {
      setNarrativeBusy(false);
    }
  }

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
          {variants && variants.variants.length > 1 && (
            <Card title="A/B breakdown">
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Variant</th>
                      <th>Subject</th>
                      <th className="num">Weight</th>
                      <th className="num">Sent</th>
                      <th className="num">Opens</th>
                      <th className="num">Clicks</th>
                      <th className="num">Open rate</th>
                      <th className="num">Click rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {variants.variants.map((v, i) => {
                      const isWinner =
                        variants.winner_variant_id === v.variant_id;
                      return (
                        <tr
                          key={v.variant_id}
                          className={isWinner ? "row-selected" : ""}
                        >
                          <td>
                            <strong>{String.fromCharCode(65 + i)}</strong>{" "}
                            {isWinner ? (
                              <span className="pill pill-active">winner</span>
                            ) : null}
                          </td>
                          <td>{v.subject || <span className="muted">—</span>}</td>
                          <td className="num">{v.weight}</td>
                          <td className="num">{v.sent}</td>
                          <td className="num">{v.unique_opens}</td>
                          <td className="num">{v.unique_clicks}</td>
                          <td className="num">
                            {(v.open_rate * 100).toFixed(1)}%
                          </td>
                          <td className="num">
                            {(v.click_rate * 100).toFixed(1)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {recipients.length > 0 && (
            <Card title={`Recipients (${recipients.length})`}>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Contact</th>
                      <th>Opened</th>
                      <th>Clicked</th>
                      <th>Replied</th>
                      <th>Status</th>
                      <th>Last activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recipients.map((r) => (
                      <tr key={r.contact_id}>
                        <td>
                          <strong>{r.name || r.email}</strong>
                          {r.name ? (
                            <div className="muted small">{r.email}</div>
                          ) : null}
                          {r.clicked_urls.length > 0 && (
                            <div className="muted small">
                              ↳ {r.clicked_urls.join(", ")}
                            </div>
                          )}
                        </td>
                        <td>{r.opened ? `Yes (${r.opens})` : "—"}</td>
                        <td>{r.clicked ? `Yes (${r.clicks})` : "—"}</td>
                        <td>
                          {r.replied ? (
                            <span className="pill pill-active">Replied</span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          {r.unsubscribed ? (
                            <span className="pill pill-unsubscribed">unsub</span>
                          ) : (
                            <span className="muted">{r.status}</span>
                          )}
                        </td>
                        <td className="muted small">
                          {r.last_activity_at
                            ? new Date(r.last_activity_at).toLocaleString()
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted small">
                Opens/clicks register only when tracking links are reachable
                (public BASE_URL); replies require IMAP reply tracking.
              </p>
            </Card>
          )}

          <Card
            title="AI summary"
            actions={
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={onGenerateNarrative}
                disabled={narrativeBusy}
              >
                {narrativeBusy
                  ? "Generating…"
                  : narrative
                    ? "Regenerate"
                    : "Generate AI summary"}
              </button>
            }
          >
            <ErrorBanner message={narrativeError} />
            {narrative ? (
              <div className="critique">
                <p>{narrative.summary}</p>
                {narrative.highlights.length > 0 && (
                  <div>
                    <h4>Highlights</h4>
                    <ul className="bullet">
                      {narrative.highlights.map((h, i) => (
                        <li key={i}>{h}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {narrative.generated_at && (
                  <p className="muted small">
                    Generated {new Date(narrative.generated_at).toLocaleString()}
                  </p>
                )}
              </div>
            ) : narrativeBusy ? (
              <Spinner label="Analyzing campaign…" />
            ) : !narrativeError ? (
              <Empty message="Generate an AI summary of this campaign's performance." />
            ) : null}
          </Card>

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
