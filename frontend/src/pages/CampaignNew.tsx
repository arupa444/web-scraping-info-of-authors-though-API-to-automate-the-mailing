import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  api,
  pollJob,
  type AiCritiqueOut,
  type AiSubjectsOut,
  type Campaign,
  type Job,
  type List,
  type SendingDomain,
} from "../lib/api";
import {
  Card,
  ErrorBanner,
  PageHeader,
  ProgressBar,
  SuccessBanner,
  errMessage,
} from "../components/ui";

const AI_DISABLED = "AI is not configured (set GEMINI_API_KEY)";

export default function CampaignNew() {
  const navigate = useNavigate();

  const [lists, setLists] = useState<List[]>([]);
  const [domains, setDomains] = useState<SendingDomain[]>([]);

  // form fields
  const [name, setName] = useState("");
  const [fromName, setFromName] = useState("");
  const [fromEmail, setFromEmail] = useState("");
  const [domainId, setDomainId] = useState("");
  const [listId, setListId] = useState("");
  const [subject, setSubject] = useState("");
  const [html, setHtml] = useState("");

  const [saved, setSaved] = useState<Campaign | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // AI subjects
  const [brief, setBrief] = useState("");
  const [tone, setTone] = useState("");
  const [aiSubjects, setAiSubjects] = useState<AiSubjectsOut["variants"]>([]);
  const [aiSubjBusy, setAiSubjBusy] = useState(false);
  const [aiSubjError, setAiSubjError] = useState<string | null>(null);

  // AI critique
  const [critique, setCritique] = useState<AiCritiqueOut | null>(null);
  const [critiqueBusy, setCritiqueBusy] = useState(false);
  const [critiqueError, setCritiqueError] = useState<string | null>(null);

  // send
  const [sendJob, setSendJob] = useState<Job | null>(null);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [l, d] = await Promise.all([
          api.get<List[]>("/api/lists"),
          api.get<SendingDomain[]>("/api/sending-domains"),
        ]);
        setLists(l);
        setDomains(d);
      } catch (err) {
        setError(errMessage(err));
      }
    })();
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setSaving(true);
    try {
      const created = await api.post<Campaign>("/api/campaigns", {
        name,
        from_name: fromName,
        from_email: fromEmail || undefined,
        sending_domain_id: domainId ? Number(domainId) : undefined,
        list_id: listId ? Number(listId) : undefined,
        variants: [{ subject, html, weight: 1 }],
      });
      setSaved(created);
      setNotice("Campaign saved. You can now send it.");
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function onGenerateSubjects() {
    setAiSubjError(null);
    setAiSubjects([]);
    setAiSubjBusy(true);
    try {
      const res = await api.post<AiSubjectsOut>("/api/ai/subjects", {
        brief: brief || name || subject,
        n: 5,
        tone: tone || undefined,
      });
      setAiSubjects(res.variants);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setAiSubjError(AI_DISABLED);
      } else {
        setAiSubjError(errMessage(err));
      }
    } finally {
      setAiSubjBusy(false);
    }
  }

  async function onCritique() {
    setCritiqueError(null);
    setCritique(null);
    setCritiqueBusy(true);
    try {
      const res = await api.post<AiCritiqueOut>("/api/ai/critique", {
        subject,
        html,
      });
      setCritique(res);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setCritiqueError(AI_DISABLED);
      } else {
        setCritiqueError(errMessage(err));
      }
    } finally {
      setCritiqueBusy(false);
    }
  }

  async function onSend() {
    if (!saved) return;
    setError(null);
    setSending(true);
    setSendJob({
      id: 0,
      type: "send",
      status: "queued",
      progress: 0,
      message: "Queuing…",
      result: null,
      error: null,
    });
    try {
      const { job_id } = await api.post<{ job_id: number }>(
        `/api/campaigns/${saved.id}/send`,
      );
      const final = await pollJob(job_id, (j) => setSendJob(j));
      if (final.status === "failed") {
        setError(final.error || "Send failed.");
      } else {
        setNotice("Campaign sent! Redirecting to analytics…");
        setTimeout(
          () => navigate(`/campaigns/${saved.id}/analytics`, { replace: true }),
          900,
        );
      }
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setSending(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="New campaign"
        subtitle="Compose your email, get AI assistance, then send."
      />
      <ErrorBanner message={error} />
      <SuccessBanner message={notice} />

      <div className="grid-2">
        <Card title="Details">
          <form onSubmit={onSave} className="form" id="campaign-form">
            <label className="field">
              <span>Campaign name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="June product update"
                required
              />
            </label>
            <div className="field-row">
              <label className="field">
                <span>From name</span>
                <input
                  value={fromName}
                  onChange={(e) => setFromName(e.target.value)}
                  placeholder="Acme Team"
                />
              </label>
              <label className="field">
                <span>From email</span>
                <input
                  type="email"
                  value={fromEmail}
                  onChange={(e) => setFromEmail(e.target.value)}
                  placeholder="hello@acme.com"
                />
              </label>
            </div>
            <div className="field-row">
              <label className="field">
                <span>Sending domain</span>
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
              <label className="field">
                <span>Recipient list</span>
                <select value={listId} onChange={(e) => setListId(e.target.value)}>
                  <option value="">— Pick a list —</option>
                  {lists.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="field">
              <span>Subject</span>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Your subject line"
                required
              />
            </label>
            <label className="field">
              <span>HTML body</span>
              <textarea
                className="code"
                rows={10}
                value={html}
                onChange={(e) => setHtml(e.target.value)}
                placeholder="<h1>Hello!</h1><p>…</p>"
              />
            </label>

            <div className="actions-row">
              <button className="btn btn-primary" disabled={saving}>
                {saving ? "Saving…" : saved ? "Update campaign" : "Save campaign"}
              </button>
              <button
                type="button"
                className="btn btn-success"
                disabled={!saved || sending}
                onClick={onSend}
              >
                {sending ? "Sending…" : "Send campaign"}
              </button>
            </div>

            {sendJob && (
              <div className="mt">
                <ProgressBar
                  value={sendJob.progress}
                  label={sendJob.message || sendJob.status}
                />
              </div>
            )}
          </form>
        </Card>

        <div className="stack">
          <Card title="AI: generate subjects">
            <ErrorBanner message={aiSubjError} />
            <div className="form">
              <label className="field">
                <span>Brief</span>
                <input
                  value={brief}
                  onChange={(e) => setBrief(e.target.value)}
                  placeholder="What is this email about?"
                />
              </label>
              <label className="field">
                <span>Tone (optional)</span>
                <input
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  placeholder="friendly, urgent, professional…"
                />
              </label>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onGenerateSubjects}
                disabled={aiSubjBusy}
              >
                {aiSubjBusy ? "Generating…" : "Generate subjects"}
              </button>
            </div>
            {aiSubjects.length > 0 && (
              <ul className="ai-suggestions mt">
                {aiSubjects.map((v, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      className="ai-pick"
                      onClick={() => setSubject(v.subject)}
                      title="Use this subject"
                    >
                      <span className="ai-subject">{v.subject}</span>
                      {v.preheader ? (
                        <span className="ai-preheader">{v.preheader}</span>
                      ) : null}
                      {v.rationale ? (
                        <span className="ai-rationale">{v.rationale}</span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="AI: check deliverability">
            <ErrorBanner message={critiqueError} />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onCritique}
              disabled={critiqueBusy}
            >
              {critiqueBusy ? "Analyzing…" : "Check deliverability"}
            </button>
            {critique && (
              <div className="critique mt">
                <div className="critique-risk">
                  Spam risk: <strong>{String(critique.spam_risk)}</strong>
                </div>
                {critique.issues.length > 0 && (
                  <div>
                    <h4>Issues</h4>
                    <ul className="bullet">
                      {critique.issues.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {critique.suggestions.length > 0 && (
                  <div>
                    <h4>Suggestions</h4>
                    <ul className="bullet">
                      {critique.suggestions.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
