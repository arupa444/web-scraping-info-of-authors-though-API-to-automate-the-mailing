import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Campaign, type List } from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  Modal,
  PageHeader,
  Spinner,
  StatusPill,
  SuccessBanner,
  errMessage,
} from "../components/ui";

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [lists, setLists] = useState<List[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  // Duplicate modal
  const [dupFor, setDupFor] = useState<Campaign | null>(null);
  const [dupName, setDupName] = useState("");
  const [dupListId, setDupListId] = useState("");

  async function load() {
    try {
      const [c, l] = await Promise.all([
        api.get<Campaign[]>("/api/campaigns"),
        api.get<List[]>("/api/lists").catch(() => []),
      ]);
      setCampaigns(c);
      setLists(l);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onSend(c: Campaign) {
    setError(null);
    setNotice(null);
    setBusyId(c.id);
    try {
      await api.post(`/api/campaigns/${c.id}/send`);
      setNotice(`"${c.name}" queued — it will send shortly.`);
      await load();
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  function openDuplicate(c: Campaign) {
    setDupFor(c);
    setDupName(`${c.name} (copy)`);
    setDupListId(c.list_id ? String(c.list_id) : "");
  }

  async function onDuplicate() {
    if (!dupFor) return;
    setError(null);
    setNotice(null);
    setBusyId(dupFor.id);
    try {
      await api.post(`/api/campaigns/${dupFor.id}/duplicate`, {
        name: dupName || undefined,
        list_id: dupListId ? Number(dupListId) : undefined,
      });
      setDupFor(null);
      setNotice("Campaign duplicated as a draft — pick it below and send.");
      await load();
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  const canSend = (s: string) => s === "draft" || s === "failed";

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
      <SuccessBanner message={notice} />

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
                      {canSend(c.status) && (
                        <>
                          <button
                            className="btn btn-primary btn-sm"
                            disabled={busyId === c.id}
                            onClick={() => onSend(c)}
                            title="Send this campaign"
                          >
                            {busyId === c.id ? "Sending…" : "Send"}
                          </button>
                          <Link
                            to={`/campaigns/${c.id}/edit`}
                            className="btn btn-ghost btn-sm"
                          >
                            Edit
                          </Link>
                        </>
                      )}
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={busyId === c.id}
                        onClick={() => openDuplicate(c)}
                        title="Duplicate to a new draft (e.g. send to another list)"
                      >
                        Duplicate
                      </button>
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

      {dupFor && (
        <Modal title="Duplicate campaign" onClose={() => setDupFor(null)}>
          <div className="form">
            <label className="field">
              <span>New campaign name</span>
              <input
                value={dupName}
                onChange={(e) => setDupName(e.target.value)}
                placeholder="Campaign name"
              />
            </label>
            <label className="field">
              <span>Send to list</span>
              <select
                value={dupListId}
                onChange={(e) => setDupListId(e.target.value)}
              >
                <option value="">— Keep original audience —</option>
                {lists.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <p className="muted small">
              Creates a fresh <strong>draft</strong> copying the content and
              sender. Pick a different list to re-send to a new audience, then
              hit <strong>Send</strong>.
            </p>
            <div className="actions-row">
              <button
                className="btn btn-primary"
                disabled={busyId === dupFor.id}
                onClick={onDuplicate}
              >
                {busyId === dupFor.id ? "Duplicating…" : "Duplicate"}
              </button>
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setDupFor(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
