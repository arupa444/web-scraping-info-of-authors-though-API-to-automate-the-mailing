import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  type ApiKey,
  type ApiKeyCreated,
  type DnsRecord,
  type SendingDomain,
  type SendingDomainCreated,
} from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  Modal,
  PageHeader,
  Spinner,
  SuccessBanner,
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

function verifyLabel(ok: boolean | undefined) {
  return (
    <span className={"verify-tag " + (ok ? "ok" : "pending")}>
      {ok ? "Verified" : "Pending"}
    </span>
  );
}

function SendingDomains() {
  const [domains, setDomains] = useState<SendingDomain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [domain, setDomain] = useState("");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [records, setRecords] = useState<Record<number, DnsRecord[]>>({});
  const [verifyBusy, setVerifyBusy] = useState<number | null>(null);

  async function load() {
    try {
      const d = await api.get<SendingDomain[]>("/api/sending-domains");
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

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    setAddError(null);
    setAdding(true);
    try {
      const res = await api.post<SendingDomainCreated>("/api/sending-domains", {
        domain,
        smtp_host: smtpHost || undefined,
        smtp_port: smtpPort ? Number(smtpPort) : undefined,
        smtp_username: smtpUser || undefined,
        smtp_password: smtpPass || undefined,
      });
      setDomains((prev) => [...prev, res.domain]);
      setRecords((prev) => ({ ...prev, [res.domain.id]: res.records }));
      setDomain("");
      setSmtpHost("");
      setSmtpUser("");
      setSmtpPass("");
    } catch (err) {
      setAddError(errMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function showDns(id: number) {
    try {
      const res = await api.get<SendingDomainCreated>(
        `/api/sending-domains/${id}/dns`,
      );
      setRecords((prev) => ({ ...prev, [id]: res.records }));
    } catch (err) {
      setError(errMessage(err));
    }
  }

  async function onVerify(id: number) {
    setVerifyBusy(id);
    try {
      const updated = await api.post<SendingDomain>(
        `/api/sending-domains/${id}/verify`,
      );
      setDomains((prev) => prev.map((d) => (d.id === id ? updated : d)));
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setVerifyBusy(null);
    }
  }

  return (
    <Card title="Sending domains">
      <ErrorBanner message={error} />
      <ErrorBanner message={addError} />

      <form onSubmit={onAdd} className="form">
        <label className="field">
          <span>Domain</span>
          <input
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="mail.acme.com"
            required
          />
        </label>
        <div className="field-row">
          <label className="field">
            <span>SMTP host (optional relay)</span>
            <input
              value={smtpHost}
              onChange={(e) => setSmtpHost(e.target.value)}
              placeholder="smtp.provider.com"
            />
          </label>
          <label className="field">
            <span>SMTP port</span>
            <input
              type="number"
              value={smtpPort}
              onChange={(e) => setSmtpPort(e.target.value)}
            />
          </label>
        </div>
        <div className="field-row">
          <label className="field">
            <span>SMTP username</span>
            <input
              value={smtpUser}
              onChange={(e) => setSmtpUser(e.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="field">
            <span>SMTP password</span>
            <input
              type="password"
              value={smtpPass}
              onChange={(e) => setSmtpPass(e.target.value)}
              autoComplete="new-password"
            />
          </label>
        </div>
        <button className="btn btn-primary" disabled={adding}>
          {adding ? "Adding…" : "Add domain"}
        </button>
      </form>

      <div className="mt">
        {loading ? (
          <Spinner />
        ) : domains.length === 0 ? (
          <Empty message="No sending domains yet." />
        ) : (
          <ul className="domain-list">
            {domains.map((d) => (
              <li key={d.id} className="domain-item">
                <div className="domain-head">
                  <strong className="mono">{d.domain}</strong>
                  <div className="verify-tags">
                    SPF {verifyLabel(d.spf_verified)} DKIM{" "}
                    {verifyLabel(d.dkim_verified)} DMARC{" "}
                    {verifyLabel(d.dmarc_verified)}
                  </div>
                  <div className="row-actions">
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => showDns(d.id)}
                    >
                      DNS records
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => onVerify(d.id)}
                      disabled={verifyBusy === d.id}
                    >
                      {verifyBusy === d.id ? "Verifying…" : "Verify"}
                    </button>
                  </div>
                </div>
                {records[d.id] && (
                  <div className="table-wrap mt">
                    <table className="table dns-table">
                      <thead>
                        <tr>
                          <th>Type</th>
                          <th>Host</th>
                          <th>Value</th>
                          <th>Purpose</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {records[d.id].map((r, i) => (
                          <tr key={i}>
                            <td className="mono">{r.type}</td>
                            <td className="mono">{r.host}</td>
                            <td className="mono dns-value">{r.value}</td>
                            <td className="muted">{r.purpose}</td>
                            <td>
                              <CopyButton value={r.value} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function ApiKeys() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [scopes, setScopes] = useState("");
  const [creating, setCreating] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);

  async function load() {
    try {
      const k = await api.get<ApiKey[]>("/api/api-keys");
      setKeys(k);
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
    setError(null);
    setCreating(true);
    try {
      const scopeList = scopes
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await api.post<ApiKeyCreated>("/api/api-keys", {
        name,
        scopes: scopeList.length ? scopeList : undefined,
      });
      setCreated(res);
      setKeys((prev) => [
        ...prev,
        { id: res.id, name: res.name, prefix: res.prefix, scopes: res.scopes },
      ]);
      setName("");
      setScopes("");
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function onRevoke(id: number) {
    const prev = keys;
    setKeys((k) => k.filter((x) => x.id !== id));
    try {
      await api.del<void>(`/api/api-keys/${id}`);
    } catch (err) {
      setError(errMessage(err));
      setKeys(prev);
    }
  }

  return (
    <Card title="API keys">
      <ErrorBanner message={error} />

      <form onSubmit={onCreate} className="form">
        <div className="field-row">
          <label className="field">
            <span>Key name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Production server"
              required
            />
          </label>
          <label className="field">
            <span>Scopes (comma separated, optional)</span>
            <input
              value={scopes}
              onChange={(e) => setScopes(e.target.value)}
              placeholder="contacts:read, campaigns:send"
            />
          </label>
        </div>
        <button className="btn btn-primary" disabled={creating}>
          {creating ? "Creating…" : "Create API key"}
        </button>
      </form>

      <div className="mt">
        {loading ? (
          <Spinner />
        ) : keys.length === 0 ? (
          <Empty message="No API keys yet." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Prefix</th>
                  <th>Scopes</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id}>
                    <td>
                      <strong>{k.name}</strong>
                    </td>
                    <td className="mono">{k.prefix}…</td>
                    <td className="muted">
                      {k.scopes?.length ? k.scopes.join(", ") : "—"}
                    </td>
                    <td className="row-actions">
                      <button
                        className="btn btn-ghost btn-sm btn-danger"
                        onClick={() => onRevoke(k.id)}
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {created && (
        <Modal title="API key created" onClose={() => setCreated(null)}>
          <SuccessBanner message="Copy this token now — it will not be shown again." />
          <div className="token-box">
            <code className="token-value">{created.token}</code>
            <CopyButton value={created.token} />
          </div>
          <p className="muted small">
            Use it as a Bearer token: <code>Authorization: Bearer {created.prefix}…</code>
          </p>
        </Modal>
      )}
    </Card>
  );
}

export default function Settings() {
  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Sending domains and API access."
      />
      <div className="stack">
        <SendingDomains />
        <ApiKeys />
      </div>
    </div>
  );
}
