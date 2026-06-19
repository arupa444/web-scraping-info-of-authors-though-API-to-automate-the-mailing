import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteTemplate,
  listTemplates,
  type Template,
} from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  Spinner,
  errMessage,
} from "../components/ui";

function formatDate(value: string | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

export default function Templates() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const t = await listTemplates();
        setTemplates(t);
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onDelete(id: number) {
    if (!window.confirm("Delete this template? This cannot be undone.")) return;
    const prev = templates;
    setDeleting(id);
    setTemplates((t) => t.filter((x) => x.id !== id));
    try {
      await deleteTemplate(id);
    } catch (err) {
      setError(errMessage(err));
      setTemplates(prev);
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Templates"
        subtitle="Build reusable email layouts with the block editor."
        actions={
          <Link to="/templates/new" className="btn btn-primary">
            New template
          </Link>
        }
      />
      <ErrorBanner message={error} />

      <Card>
        {loading ? (
          <Spinner label="Loading templates…" />
        ) : templates.length === 0 ? (
          <Empty message="No templates yet. Create your first one." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Subject</th>
                  <th>Updated</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {templates.map((t) => (
                  <tr key={t.id}>
                    <td>
                      <strong>{t.name}</strong>
                    </td>
                    <td className="muted">{t.subject || "—"}</td>
                    <td className="muted">{formatDate(t.updated_at)}</td>
                    <td className="row-actions">
                      <Link
                        to={`/templates/${t.id}`}
                        className="btn btn-ghost btn-sm"
                      >
                        Edit
                      </Link>
                      <button
                        className="btn btn-ghost btn-sm btn-danger"
                        onClick={() => onDelete(t.id)}
                        disabled={deleting === t.id}
                      >
                        {deleting === t.id ? "Deleting…" : "Delete"}
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
