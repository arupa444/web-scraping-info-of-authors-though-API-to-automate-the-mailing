import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  createForm,
  deleteForm,
  listForms,
  type List,
  type SendingDomain,
  type SignupForm,
} from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  Spinner,
  errMessage,
} from "../components/ui";

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="btn btn-ghost btn-sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function formUrl(id: number): string {
  return `${window.location.origin}/f/${id}`;
}

export default function Forms() {
  const [forms, setForms] = useState<SignupForm[]>([]);
  const [lists, setLists] = useState<List[]>([]);
  const [domains, setDomains] = useState<SendingDomain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // create
  const [name, setName] = useState("");
  const [listId, setListId] = useState("");
  const [domainId, setDomainId] = useState("");
  const [doubleOptin, setDoubleOptin] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function load() {
    try {
      const [f, l, d] = await Promise.all([
        listForms(),
        api.get<List[]>("/api/lists"),
        api.get<SendingDomain[]>("/api/sending-domains"),
      ]);
      setForms(f);
      setLists(l);
      setDomains(d);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreateError(null);
    setCreating(true);
    try {
      const created = await createForm({
        name,
        list_id: listId ? Number(listId) : undefined,
        sending_domain_id: domainId ? Number(domainId) : undefined,
        double_optin: doubleOptin,
        success_message: successMessage || undefined,
      });
      setForms((prev) => [...prev, created]);
      setName("");
      setListId("");
      setDomainId("");
      setDoubleOptin(false);
      setSuccessMessage("");
    } catch (err) {
      setCreateError(errMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(id: number) {
    const prev = forms;
    setForms((f) => f.filter((x) => x.id !== id));
    try {
      await deleteForm(id);
    } catch (err) {
      setError(errMessage(err));
      setForms(prev);
    }
  }

  return (
    <div>
      <PageHeader
        title="Forms"
        subtitle="Hosted signup forms that grow your lists."
      />
      <ErrorBanner message={error} />

      <div className="grid-2">
        <Card title="Create a form">
          <ErrorBanner message={createError} />
          <form onSubmit={onCreate} className="form">
            <label className="field">
              <span>Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Newsletter signup"
                required
              />
            </label>
            <div className="field-row">
              <label className="field">
                <span>Target list</span>
                <select
                  value={listId}
                  onChange={(e) => setListId(e.target.value)}
                >
                  <option value="">— Pick a list —</option>
                  {lists.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                <span>Sending domain (for opt-in)</span>
                <select
                  value={domainId}
                  onChange={(e) => setDomainId(e.target.value)}
                >
                  <option value="">— Default —</option>
                  {domains.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.domain}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="field">
              <span>Success message</span>
              <input
                value={successMessage}
                onChange={(e) => setSuccessMessage(e.target.value)}
                placeholder="Thanks for subscribing!"
              />
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={doubleOptin}
                onChange={(e) => setDoubleOptin(e.target.checked)}
              />
              <span>Require double opt-in (confirmation email)</span>
            </label>
            <button className="btn btn-primary" disabled={creating}>
              {creating ? "Creating…" : "Create form"}
            </button>
          </form>
        </Card>

        <Card title="Your forms">
          {loading ? (
            <Spinner />
          ) : forms.length === 0 ? (
            <Empty message="No forms yet." />
          ) : (
            <ul className="domain-list">
              {forms.map((f) => (
                <li key={f.id} className="domain-item">
                  <div className="domain-head">
                    <div className="simple-list-main">
                      <strong>{f.name}</strong>
                      <span className="muted small">
                        {f.double_optin ? "Double opt-in" : "Single opt-in"}
                      </span>
                    </div>
                    <div className="row-actions">
                      <button
                        className="btn btn-ghost btn-sm btn-danger"
                        onClick={() => onDelete(f.id)}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <div className="token-box mt">
                    <code className="token-value">{formUrl(f.id)}</code>
                    <CopyButton value={formUrl(f.id)} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
