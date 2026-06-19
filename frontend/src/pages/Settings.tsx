import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  ApiError,
  api,
  checkout,
  createMember,
  createOutboundWebhook,
  deleteMember,
  deleteOutboundWebhook,
  getBilling,
  getPlans,
  listAuditLogs,
  getReplyWebhook,
  listMembers,
  listOutboundWebhooks,
  updateSendingDomain,
  type ApiKey,
  type ApiKeyCreated,
  type AuditLog,
  type Billing,
  type BillingPlan,
  type DnsRecord,
  type Member,
  type OutboundWebhook,
  type SendingDomain,
  type SendingDomainCreated,
  type SendingProvider,
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

// Common SMTP relays for the dropdown. The host/port fields stay fully editable,
// and a "Custom…" option lets users enter any other server. Add more here freely.
const SMTP_PRESETS: { label: string; host: string; port: number }[] = [
  { label: "Zoho Mail (India · smtp.zoho.in)", host: "smtp.zoho.in", port: 587 },
  { label: "Zoho Mail (Global · smtp.zoho.com)", host: "smtp.zoho.com", port: 587 },
  { label: "Zoho Mail (EU · smtp.zoho.eu)", host: "smtp.zoho.eu", port: 587 },
  { label: "Gmail / Google Workspace", host: "smtp.gmail.com", port: 587 },
  { label: "Outlook / Microsoft 365", host: "smtp.office365.com", port: 587 },
  { label: "Yahoo Mail", host: "smtp.mail.yahoo.com", port: 587 },
  { label: "Amazon SES (us-east-1)", host: "email-smtp.us-east-1.amazonaws.com", port: 587 },
  { label: "Amazon SES (eu-west-1)", host: "email-smtp.eu-west-1.amazonaws.com", port: 587 },
  { label: "Mailgun", host: "smtp.mailgun.org", port: 587 },
  { label: "SendGrid (SMTP)", host: "smtp.sendgrid.net", port: 587 },
  { label: "Brevo (Sendinblue)", host: "smtp-relay.brevo.com", port: 587 },
  { label: "Postmark", host: "smtp.postmarkapp.com", port: 587 },
  { label: "Mailjet", host: "in-v3.mailjet.com", port: 587 },
  { label: "iCloud Mail", host: "smtp.mail.me.com", port: 587 },
];

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

// Per-domain reply tracking: enable POP3 polling (no paid IMAP needed) so
// replies show up as the "Replies" metric in campaign analytics.
function ReplyTrackingEditor({
  domain,
  onSaved,
  inboundUrl,
}: {
  domain: SendingDomain;
  onSaved: () => void;
  inboundUrl: string;
}) {
  const [open, setOpen] = useState(false);
  const [replyTo, setReplyTo] = useState(domain.reply_to || "");
  const [protocol, setProtocol] = useState(domain.reply_protocol || "");
  const [host, setHost] = useState(domain.reply_host || "");
  const [port, setPort] = useState(String(domain.reply_port || 993));
  const [username, setUsername] = useState(domain.reply_username || "");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    setErr(null);
    setMsg(null);
    setBusy(true);
    try {
      await updateSendingDomain(domain.id, {
        reply_to: replyTo,
        reply_protocol: protocol,
        reply_host: host,
        reply_port: Number(port) || 993,
        reply_username: username,
        ...(password ? { reply_password: password } : {}),
      });
      setMsg("Reply settings saved.");
      setPassword("");
      onSaved();
    } catch (e) {
      setErr(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt">
      <button className="btn btn-ghost btn-sm" onClick={() => setOpen(!open)}>
        {open
          ? "Hide reply tracking"
          : domain.reply_protocol
            ? `Reply tracking: ${domain.reply_protocol.toUpperCase()} ✓`
            : "Set up reply tracking"}
      </button>
      {open && (
        <div className="form mt">
          <ErrorBanner message={err} />
          <SuccessBanner message={msg} />

          <label className="field">
            <span>Reply-To address</span>
            <input
              value={replyTo}
              onChange={(e) => setReplyTo(e.target.value)}
              placeholder="replies@yourdomain.com (or a free Gmail address)"
              autoComplete="off"
            />
          </label>
          <p className="muted small">
            Replies go to this address. Since Zoho POP/IMAP need a paid plan, point
            Reply-To at a mailbox you can read for free — see the two options below.
          </p>

          <div className="callout">
            <strong>Option A — free Gmail inbox (easiest):</strong> set Reply-To to a
            Gmail address, then below choose <strong>IMAP</strong> with{" "}
            <code>imap.gmail.com:993</code> and a Gmail app password. Gmail IMAP is free.
            <br />
            <strong>Option B — inbound webhook (no mailbox):</strong> forward replies to
            this URL (e.g. free Cloudflare Email Routing on a subdomain, or SendGrid
            Inbound Parse) — they’ll be matched automatically:
            <div className="field-row" style={{ alignItems: "center", marginTop: "6px" }}>
              <input className="mono" readOnly value={inboundUrl} />
              <CopyButton value={inboundUrl} />
            </div>
          </div>

          <div className="field-row">
            <label className="field">
              <span>Protocol</span>
              <select
                value={protocol}
                onChange={(e) => {
                  const v = e.target.value;
                  setProtocol(v);
                  // Sensible default port per protocol (only if still at a default).
                  if (v === "imap" && (port === "995" || port === "")) setPort("993");
                  if (v === "pop3" && (port === "993" || port === "")) setPort("995");
                }}
              >
                <option value="">Off</option>
                <option value="imap">IMAP (recommended)</option>
                <option value="pop3">POP3</option>
              </select>
            </label>
            <label className="field">
              <span>Host</span>
              <input
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder={protocol === "pop3" ? "pop.zoho.in" : "imap.zoho.in"}
              />
            </label>
            <label className="field">
              <span>Port</span>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value)}
              />
            </label>
          </div>
          <div className="field-row">
            <label className="field">
              <span>Mailbox username</span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="team@influenceai.in"
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>
                Mailbox password
                {domain.reply_protocol ? " (blank = keep current)" : ""}
              </span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </label>
          </div>
          <p className="muted small">
            IMAP fetches only new messages (read-only — it never marks your mail
            as read or deletes it). Enable IMAP/POP in your mailbox provider
            (e.g. Zoho → Settings → Mail Accounts), then replies show up as the{" "}
            <strong>Replies</strong> metric in campaign analytics.
          </p>
          <div className="actions-row">
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={save}>
              {busy ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SendingDomains() {
  const [domains, setDomains] = useState<SendingDomain[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [domain, setDomain] = useState("");
  const [provider, setProvider] = useState<SendingProvider>("smtp");
  const [apiKey, setApiKey] = useState("");
  const [smtpHost, setSmtpHost] = useState(SMTP_PRESETS[0].host);
  const [smtpPort, setSmtpPort] = useState(String(SMTP_PRESETS[0].port));
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [verifyTls, setVerifyTls] = useState(true);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [records, setRecords] = useState<Record<number, DnsRecord[]>>({});
  const [verifyBusy, setVerifyBusy] = useState<number | null>(null);
  const [inboundUrl, setInboundUrl] = useState("");

  const usesApiKey = provider === "resend" || provider === "sendgrid";

  async function load() {
    try {
      const [d, wh] = await Promise.all([
        api.get<SendingDomain[]>("/api/sending-domains"),
        getReplyWebhook().catch(() => ({ url: "" })),
      ]);
      setDomains(d);
      setInboundUrl(wh.url);
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
        provider,
        api_key: usesApiKey ? apiKey || undefined : undefined,
        smtp_host: !usesApiKey ? smtpHost || undefined : undefined,
        smtp_port: !usesApiKey && smtpPort ? Number(smtpPort) : undefined,
        smtp_username: !usesApiKey ? smtpUser || undefined : undefined,
        smtp_password: !usesApiKey ? smtpPass || undefined : undefined,
        verify_tls: verifyTls,
      });
      setDomains((prev) => [...prev, res.domain]);
      setRecords((prev) => ({ ...prev, [res.domain.id]: res.records }));
      setDomain("");
      setApiKey("");
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
        <div className="field-row">
          <label className="field">
            <span>Domain</span>
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="mail.acme.com"
              required
            />
          </label>
          <label className="field">
            <span>Provider</span>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value as SendingProvider)}
            >
              <option value="smtp">SMTP</option>
              <option value="resend">Resend</option>
              <option value="sendgrid">SendGrid</option>
            </select>
          </label>
        </div>

        {usesApiKey ? (
          <label className="field">
            <span>API key</span>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="re_… / SG.…"
              autoComplete="new-password"
            />
          </label>
        ) : (
          <>
            <label className="field">
              <span>SMTP provider</span>
              <select
                value={SMTP_PRESETS.find((p) => p.host === smtpHost)?.host ?? "custom"}
                onChange={(e) => {
                  const preset = SMTP_PRESETS.find((p) => p.host === e.target.value);
                  if (preset) {
                    setSmtpHost(preset.host);
                    setSmtpPort(String(preset.port));
                  } else {
                    setSmtpHost(""); // Custom — type your own host/port below
                  }
                }}
              >
                {SMTP_PRESETS.map((p) => (
                  <option key={p.host} value={p.host}>
                    {p.label}
                  </option>
                ))}
                <option value="custom">Custom / other…</option>
              </select>
            </label>
            <div className="field-row">
              <label className="field">
                <span>SMTP host</span>
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
            <label className="field-check">
              <input
                type="checkbox"
                checked={verifyTls}
                onChange={(e) => setVerifyTls(e.target.checked)}
              />
              <span>Verify TLS certificate (recommended; uncheck only for a trusted self-signed relay)</span>
            </label>
          </>
        )}
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
                  <div className="simple-list-main">
                    <strong className="mono">{d.domain}</strong>
                    {d.provider ? (
                      <span className="pill">{d.provider}</span>
                    ) : null}
                  </div>
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
                <ReplyTrackingEditor domain={d} onSaved={load} inboundUrl={inboundUrl} />
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
        scopes: scopeList.join(","), // backend expects a comma-separated string
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

      <p className="muted small">
        Use your API key with the public REST API as a Bearer token:{" "}
        <code>Authorization: Bearer YOUR_KEY</code>
      </p>

      <form onSubmit={onCreate} className="form mt">
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
                      {k.scopes ? k.scopes : "—"}
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
            Use it as a Bearer token:{" "}
            <code>Authorization: Bearer {created.prefix}…</code>
          </p>
        </Modal>
      )}
    </Card>
  );
}

function OutboundWebhooks() {
  const [hooks, setHooks] = useState<OutboundWebhook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [url, setUrl] = useState("");
  const [events, setEvents] = useState("");
  const [active, setActive] = useState(true);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function load() {
    try {
      const h = await listOutboundWebhooks();
      setHooks(h);
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
      const created = await createOutboundWebhook({ url, events, active });
      setHooks((prev) => [...prev, created]);
      setUrl("");
      setEvents("");
      setActive(true);
    } catch (err) {
      setCreateError(errMessage(err));
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(id: number) {
    const prev = hooks;
    setHooks((h) => h.filter((x) => x.id !== id));
    try {
      await deleteOutboundWebhook(id);
    } catch (err) {
      setError(errMessage(err));
      setHooks(prev);
    }
  }

  return (
    <Card title="Outbound webhooks">
      <ErrorBanner message={error} />
      <ErrorBanner message={createError} />

      <form onSubmit={onCreate} className="form">
        <label className="field">
          <span>Endpoint URL</span>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/hooks/icereach"
            required
          />
        </label>
        <label className="field">
          <span>Events (comma separated)</span>
          <input
            value={events}
            onChange={(e) => setEvents(e.target.value)}
            placeholder="open, click, unsubscribe, bounce"
            required
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          <span>Active</span>
        </label>
        <button className="btn btn-primary" disabled={creating}>
          {creating ? "Adding…" : "Add webhook"}
        </button>
      </form>

      <div className="mt">
        {loading ? (
          <Spinner />
        ) : hooks.length === 0 ? (
          <Empty message="No outbound webhooks yet." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>URL</th>
                  <th>Events</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {hooks.map((h) => (
                  <tr key={h.id}>
                    <td className="mono">{h.url}</td>
                    <td className="muted">{h.events || "—"}</td>
                    <td>
                      <span
                        className={"pill " + (h.active ? "pill-active" : "")}
                      >
                        {h.active ? "active" : "paused"}
                      </span>
                    </td>
                    <td className="row-actions">
                      <button
                        className="btn btn-ghost btn-sm btn-danger"
                        onClick={() => onDelete(h.id)}
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
      </div>
    </Card>
  );
}

function Members({ role }: { role: string }) {
  const canManage = role === "owner" || role === "admin";
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newRole, setNewRole] = useState("member");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  async function load() {
    try {
      const m = await listMembers();
      setMembers(m);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError(errMessage(err));
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onInvite(e: FormEvent) {
    e.preventDefault();
    setInviteError(null);
    setInviting(true);
    try {
      const created = await createMember({ email, password, role: newRole });
      setMembers((prev) => [...prev, created]);
      setEmail("");
      setPassword("");
      setNewRole("member");
    } catch (err) {
      setInviteError(errMessage(err));
    } finally {
      setInviting(false);
    }
  }

  async function onRemove(userId: number) {
    const prev = members;
    setMembers((m) => m.filter((x) => x.user_id !== userId));
    try {
      await deleteMember(userId);
    } catch (err) {
      setError(errMessage(err));
      setMembers(prev);
    }
  }

  return (
    <Card title="Team">
      <ErrorBanner message={error} />

      {forbidden ? (
        <Empty message="You don't have permission to manage team members." />
      ) : (
        <>
          {canManage && (
            <form onSubmit={onInvite} className="form">
              <ErrorBanner message={inviteError} />
              <div className="field-row">
                <label className="field">
                  <span>Email</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="teammate@acme.com"
                    required
                  />
                </label>
                <label className="field">
                  <span>Temporary password</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    required
                  />
                </label>
              </div>
              <label className="field">
                <span>Role</span>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value)}
                >
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                  <option value="owner">Owner</option>
                </select>
              </label>
              <button className="btn btn-primary" disabled={inviting}>
                {inviting ? "Inviting…" : "Invite member"}
              </button>
            </form>
          )}

          <div className="mt">
            {loading ? (
              <Spinner />
            ) : members.length === 0 ? (
              <Empty message="No team members yet." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Name</th>
                      <th>Role</th>
                      {canManage ? <th></th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {members.map((m) => (
                      <tr key={m.user_id}>
                        <td className="mono">{m.email}</td>
                        <td>{m.name || <span className="muted">—</span>}</td>
                        <td>
                          <span className="pill">{m.role}</span>
                        </td>
                        {canManage ? (
                          <td className="row-actions">
                            <button
                              className="btn btn-ghost btn-sm btn-danger"
                              onClick={() => onRemove(m.user_id)}
                            >
                              Remove
                            </button>
                          </td>
                        ) : null}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function BillingSection() {
  const [billing, setBilling] = useState<Billing | null>(null);
  const [plans, setPlans] = useState<BillingPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);

  async function load() {
    try {
      const [b, p] = await Promise.all([getBilling(), getPlans()]);
      setBilling(b);
      setPlans(p);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function onSwitch(plan: string) {
    setError(null);
    setNotice(null);
    setSwitching(plan);
    try {
      const res = await checkout(plan);
      if (res.applied) {
        setNotice(res.note || "Plan updated.");
        await load();
      } else if (res.checkout_url) {
        window.location.assign(res.checkout_url);
      } else {
        setNotice(res.note || "Checkout started.");
      }
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setSwitching(null);
    }
  }

  return (
    <Card title="Billing (preview)">
      <ErrorBanner message={error} />
      <SuccessBanner message={notice} />
      <p className="muted small">
        This billing flow is a scaffold — checkout does not charge a real card.
      </p>

      {loading ? (
        <Spinner />
      ) : (
        <>
          {billing && (
            <div className="metric-grid mt">
              <div className="metric-card">
                <span className="metric-label">Current plan</span>
                <span className="metric-value">{billing.plan}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Sent this month</span>
                <span className="metric-value">{billing.sent_this_month}</span>
              </div>
              <div className="metric-card">
                <span className="metric-label">Monthly limit</span>
                <span className="metric-value">
                  {billing.monthly_send_limit}
                </span>
              </div>
            </div>
          )}

          <div className="mt">
            {plans.length === 0 ? (
              <Empty message="No plans available." />
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Plan</th>
                      <th>Monthly sends</th>
                      <th>Price</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {plans.map((p) => {
                      const current = billing?.plan === p.key;
                      return (
                        <tr key={p.key}>
                          <td>
                            <strong>{p.name}</strong>{" "}
                            {current ? (
                              <span className="pill pill-active">current</span>
                            ) : null}
                          </td>
                          <td>{p.monthly_send_limit}</td>
                          <td>${p.price_usd}/mo</td>
                          <td className="row-actions">
                            <button
                              className="btn btn-secondary btn-sm"
                              onClick={() => onSwitch(p.key)}
                              disabled={current || switching === p.key}
                            >
                              {switching === p.key
                                ? "Switching…"
                                : current
                                  ? "Current"
                                  : "Switch plan"}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function AuditLogs() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  async function load() {
    try {
      const l = await listAuditLogs();
      setLogs(l);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
      } else {
        setError(errMessage(err));
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <Card title="Audit log">
      <ErrorBanner message={error} />
      {loading ? (
        <Spinner />
      ) : forbidden ? (
        <Empty message="Admins only." />
      ) : logs.length === 0 ? (
        <Empty message="No audit entries yet." />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>Action</th>
                <th>Target</th>
                <th>User</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l) => (
                <tr key={l.id}>
                  <td className="muted">
                    {new Date(l.created_at).toLocaleString()}
                  </td>
                  <td className="mono">{l.action}</td>
                  <td className="muted">{l.target || "—"}</td>
                  <td className="mono">#{l.user_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

const TABS = [
  { key: "domains", label: "Sending domains" },
  { key: "apikeys", label: "API keys" },
  { key: "webhooks", label: "Outbound webhooks" },
  { key: "team", label: "Team" },
  { key: "billing", label: "Billing" },
  { key: "audit", label: "Audit log" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function Settings() {
  const { me } = useAuth();
  const role = me?.role ?? "member";
  const [tab, setTab] = useState<TabKey>("domains");

  return (
    <div>
      <PageHeader
        title="Settings"
        subtitle="Workspace console — sending, integrations, team and billing."
      />

      <div className="seg-mode mt-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={"chip" + (tab === t.key ? " chip-active" : "")}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="stack mt">
        {tab === "domains" && <SendingDomains />}
        {tab === "apikeys" && <ApiKeys />}
        {tab === "webhooks" && <OutboundWebhooks />}
        {tab === "team" && <Members role={role} />}
        {tab === "billing" && <BillingSection />}
        {tab === "audit" && <AuditLogs />}
      </div>
    </div>
  );
}
