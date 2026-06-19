import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  activateAutomation,
  deleteAutomation,
  listAutomations,
  pauseAutomation,
  type Automation,
} from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  Spinner,
  StatusPill,
  errMessage,
} from "../components/ui";

const TRIGGER_LABELS: Record<Automation["trigger_type"], string> = {
  manual: "Manual",
  list_subscribe: "List subscribe",
};

export default function Automations() {
  const navigate = useNavigate();
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const a = await listAutomations();
        setAutomations(a);
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onToggle(a: Automation) {
    setError(null);
    setBusyId(a.id);
    try {
      const updated =
        a.status === "active"
          ? await pauseAutomation(a.id)
          : await activateAutomation(a.id);
      setAutomations((prev) =>
        prev.map((x) => (x.id === a.id ? updated : x)),
      );
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(a: Automation) {
    if (!window.confirm(`Delete automation "${a.name}"?`)) return;
    const prev = automations;
    setAutomations((s) => s.filter((x) => x.id !== a.id));
    try {
      await deleteAutomation(a.id);
    } catch (err) {
      setError(errMessage(err));
      setAutomations(prev);
    }
  }

  return (
    <div>
      <PageHeader
        title="Automations"
        subtitle="Multi-step journeys that send on triggers and timers."
        actions={
          <Link to="/automations/new" className="btn btn-primary">
            New automation
          </Link>
        }
      />
      <ErrorBanner message={error} />

      <Card>
        {loading ? (
          <Spinner label="Loading automations…" />
        ) : automations.length === 0 ? (
          <Empty message="No automations yet. Create your first journey." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Trigger</th>
                  <th>Steps</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {automations.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <Link to={`/automations/${a.id}`}>
                        <strong>{a.name}</strong>
                      </Link>
                    </td>
                    <td className="muted">{TRIGGER_LABELS[a.trigger_type]}</td>
                    <td className="num">{a.steps?.length ?? 0}</td>
                    <td>
                      <StatusPill status={a.status} />
                    </td>
                    <td className="row-actions">
                      <button
                        className="btn btn-ghost btn-sm"
                        disabled={busyId === a.id || a.status === "draft"}
                        title={
                          a.status === "draft"
                            ? "Open the builder to activate"
                            : a.status === "active"
                              ? "Pause"
                              : "Activate"
                        }
                        onClick={() => onToggle(a)}
                      >
                        {busyId === a.id
                          ? "…"
                          : a.status === "active"
                            ? "Pause"
                            : "Activate"}
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => navigate(`/automations/${a.id}`)}
                      >
                        Edit
                      </button>
                      <button
                        className="btn btn-ghost btn-sm btn-danger"
                        onClick={() => onDelete(a)}
                      >
                        Delete
                      </button>
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
