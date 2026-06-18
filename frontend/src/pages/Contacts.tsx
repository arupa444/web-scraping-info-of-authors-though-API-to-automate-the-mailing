import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  api,
  pollJob,
  type Contact,
  type Job,
  type List,
} from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  ProgressBar,
  Spinner,
  StatusPill,
  SuccessBanner,
  errMessage,
} from "../components/ui";

export default function Contacts() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [lists, setLists] = useState<List[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // add form
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // import
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [importListId, setImportListId] = useState<string>("");
  const [validateEmails, setValidateEmails] = useState(false);
  const [importJob, setImportJob] = useState<Job | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importDone, setImportDone] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);

  async function load() {
    try {
      const [c, l] = await Promise.all([
        api.get<Contact[]>("/api/contacts"),
        api.get<List[]>("/api/lists"),
      ]);
      setContacts(c);
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

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    setAddError(null);
    setAdding(true);
    try {
      const created = await api.post<Contact>("/api/contacts", {
        email,
        name: name || undefined,
      });
      setContacts((prev) => [created, ...prev]);
      setEmail("");
      setName("");
    } catch (err) {
      setAddError(errMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function onDelete(id: number) {
    const prev = contacts;
    setContacts((c) => c.filter((x) => x.id !== id));
    try {
      await api.del<void>(`/api/contacts/${id}`);
    } catch (err) {
      setError(errMessage(err));
      setContacts(prev);
    }
  }

  async function onImport(e: FormEvent) {
    e.preventDefault();
    setImportError(null);
    setImportDone(null);
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setImportError("Choose a CSV or XLSX file first.");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    if (importListId) form.append("list_id", importListId);
    form.append("validate_emails", String(validateEmails));

    setImporting(true);
    setImportJob({ id: 0, type: "import", status: "queued", progress: 0, message: "Uploading…", result: null, error: null });
    try {
      const { job_id } = await api.postForm<{ job_id: number }>(
        "/api/contacts/import",
        form,
      );
      const final = await pollJob(job_id, (j) => setImportJob(j));
      if (final.status === "failed") {
        setImportError(final.error || "Import failed.");
      } else {
        const r = final.result || {};
        const parts = Object.entries(r)
          .filter(([, v]) => typeof v === "number" || typeof v === "string")
          .map(([k, v]) => `${k}: ${v}`);
        setImportDone(
          parts.length ? `Import complete — ${parts.join(", ")}` : "Import complete.",
        );
        if (fileRef.current) fileRef.current.value = "";
        await load();
      }
    } catch (err) {
      setImportError(errMessage(err));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div>
      <PageHeader title="Contacts" subtitle="Everyone you can email." />
      <ErrorBanner message={error} />

      <div className="grid-2">
        <Card title="Add contact">
          <ErrorBanner message={addError} />
          <form onSubmit={onAdd} className="form">
            <label className="field">
              <span>Email</span>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="person@company.com"
                required
              />
            </label>
            <label className="field">
              <span>Name (optional)</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Jane Doe"
              />
            </label>
            <button className="btn btn-primary" disabled={adding}>
              {adding ? "Adding…" : "Add contact"}
            </button>
          </form>
        </Card>

        <Card title="Import from file">
          <ErrorBanner message={importError} />
          <SuccessBanner message={importDone} />
          <form onSubmit={onImport} className="form">
            <label className="field">
              <span>CSV or XLSX file</span>
              <input ref={fileRef} type="file" accept=".csv,.xlsx" />
            </label>
            <label className="field">
              <span>Add to list (optional)</span>
              <select
                value={importListId}
                onChange={(e) => setImportListId(e.target.value)}
              >
                <option value="">— None —</option>
                {lists.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={validateEmails}
                onChange={(e) => setValidateEmails(e.target.checked)}
              />
              <span>Validate email addresses during import</span>
            </label>
            <button className="btn btn-primary" disabled={importing}>
              {importing ? "Importing…" : "Start import"}
            </button>
          </form>
          {importJob && importJob.status !== "done" && (
            <div className="mt">
              <ProgressBar
                value={importJob.progress}
                label={importJob.message || importJob.status}
              />
            </div>
          )}
        </Card>
      </div>

      <Card title={`All contacts (${contacts.length})`}>
        {loading ? (
          <Spinner label="Loading contacts…" />
        ) : contacts.length === 0 ? (
          <Empty message="No contacts yet. Add one or import a file to get started." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Name</th>
                  <th>Status</th>
                  <th className="num">Attributes</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.email}</td>
                    <td>{c.name || <span className="muted">—</span>}</td>
                    <td>
                      <StatusPill status={c.status} />
                    </td>
                    <td className="num muted">
                      {Object.keys(c.attributes || {}).length || 0}
                    </td>
                    <td className="row-actions">
                      <button
                        className="btn btn-ghost btn-sm btn-danger"
                        onClick={() => onDelete(c.id)}
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
