import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ApiError,
  activateAutomation,
  api,
  createAutomation,
  draftSequence,
  enrollAutomation,
  getAutomation,
  getAutomationRuns,
  getTemplate,
  listTemplates,
  pauseAutomation,
  renderTemplate,
  updateAutomation,
  type Automation,
  type AutomationIn,
  type AutomationRun,
  type AutomationStep,
  type List,
  type Segment,
  type SendingDomain,
  type StepType,
  type Template,
  type TriggerType,
} from "../lib/api";
import {
  Card,
  ErrorBanner,
  Modal,
  PageHeader,
  Spinner,
  StatusPill,
  SuccessBanner,
  errMessage,
} from "../components/ui";

const AI_DISABLED = "AI is not configured (set GEMINI_API_KEY)";

const STEP_PALETTE: { type: StepType; label: string }[] = [
  { type: "send", label: "Send email" },
  { type: "wait", label: "Wait" },
  { type: "condition", label: "Condition" },
];

const STEP_LABELS: Record<StepType, string> = {
  send: "Send email",
  wait: "Wait",
  condition: "Condition",
};

const RULE_OPS = [
  { value: "eq", label: "equals" },
  { value: "neq", label: "not equals" },
  { value: "contains", label: "contains" },
  { value: "gt", label: "greater than" },
  { value: "lt", label: "less than" },
  { value: "in", label: "in" },
  { value: "exists", label: "exists" },
];

function newStep(type: StepType): AutomationStep {
  switch (type) {
    case "send":
      return { type: "send", config: { subject: "", html: "" } };
    case "wait":
      return { type: "wait", config: { delay_days: 1 } };
    case "condition":
      return { type: "condition", config: { rules: { all: [] } } };
  }
}

// ---------------------------------------------------------------------------
// Condition rule helpers — the segment DSL: { all|any: [ {field, op, value} ] }
// ---------------------------------------------------------------------------

interface RuleRow {
  field: string;
  op: string;
  value: string;
}
type RulesObject = Record<string, unknown>;

function rulesMatch(rules: RulesObject): "all" | "any" {
  return "any" in rules && !("all" in rules) ? "any" : "all";
}

function rulesToRows(rules: RulesObject): RuleRow[] {
  const key = rulesMatch(rules);
  const raw = rules[key];
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (r): r is { field: string; op: string; value?: unknown } =>
        !!r && typeof r === "object" && "field" in r,
    )
    .map((r) => ({
      field: String(r.field ?? ""),
      op: String(r.op ?? "eq"),
      value: r.value === undefined ? "" : String(r.value),
    }));
}

function buildRules(match: "all" | "any", rows: RuleRow[]): RulesObject {
  return {
    [match]: rows
      .filter((r) => r.field.trim())
      .map((r) =>
        r.op === "exists"
          ? { field: r.field.trim(), op: r.op }
          : { field: r.field.trim(), op: r.op, value: r.value },
      ),
  };
}

// ---------------------------------------------------------------------------
// Per-step editors
// ---------------------------------------------------------------------------

function SendStepEditor({
  config,
  templates,
  onChange,
}: {
  config: Record<string, unknown>;
  templates: Template[];
  onChange: (next: Record<string, unknown>) => void;
}) {
  const subject = typeof config.subject === "string" ? config.subject : "";
  const html = typeof config.html === "string" ? config.html : "";
  const [picking, setPicking] = useState("");

  async function onPickTemplate(id: string) {
    setPicking(id);
    if (!id) return;
    try {
      const [tmpl, rendered] = await Promise.all([
        getTemplate(id),
        renderTemplate(id),
      ]);
      onChange({ ...config, subject: tmpl.subject, html: rendered.html });
    } finally {
      setPicking("");
    }
  }

  return (
    <div className="form">
      {templates.length > 0 && (
        <label className="field">
          <span>Prefill from template (optional)</span>
          <select
            value={picking}
            onChange={(e) => onPickTemplate(e.target.value)}
          >
            <option value="">— Blank —</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="field">
        <span>Subject</span>
        <input
          value={subject}
          onChange={(e) => onChange({ ...config, subject: e.target.value })}
          placeholder="Your subject line"
        />
      </label>
      <label className="field">
        <span>HTML body</span>
        <textarea
          className="code"
          rows={8}
          value={html}
          onChange={(e) => onChange({ ...config, html: e.target.value })}
          placeholder="<h1>Hello!</h1><p>…</p>"
        />
      </label>
    </div>
  );
}

function WaitStepEditor({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const delayDays =
    typeof config.delay_days === "number" ? config.delay_days : 1;
  return (
    <div className="form">
      <label className="field">
        <span>Delay (days)</span>
        <input
          type="number"
          min={0}
          value={delayDays}
          onChange={(e) =>
            onChange({ delay_days: Number(e.target.value) || 0 })
          }
        />
      </label>
    </div>
  );
}

function ConditionStepEditor({
  config,
  onChange,
}: {
  config: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  const rules: RulesObject =
    config.rules && typeof config.rules === "object"
      ? (config.rules as RulesObject)
      : { all: [] };
  const [mode, setMode] = useState<"builder" | "json">("builder");
  const [json, setJson] = useState(() => JSON.stringify(rules, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  const match = rulesMatch(rules);
  const rows = rulesToRows(rules);

  const setRules = (next: RulesObject) => onChange({ ...config, rules: next });

  function updateRow(i: number, patch: Partial<RuleRow>) {
    const next = rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r));
    setRules(buildRules(match, next));
  }
  function addRow() {
    setRules(buildRules(match, [...rows, { field: "", op: "eq", value: "" }]));
  }
  function removeRow(i: number) {
    setRules(buildRules(match, rows.filter((_, idx) => idx !== i)));
  }
  function setMatch(next: "all" | "any") {
    setRules(buildRules(next, rows));
  }

  function applyJson(text: string) {
    setJson(text);
    try {
      const parsed = JSON.parse(text);
      setJsonError(null);
      setRules(parsed);
    } catch {
      setJsonError("Rules must be valid JSON.");
    }
  }

  return (
    <div className="form">
      <div className="seg-mode">
        <button
          type="button"
          className={"chip" + (mode === "builder" ? " chip-active" : "")}
          onClick={() => setMode("builder")}
        >
          Rule builder
        </button>
        <button
          type="button"
          className={"chip" + (mode === "json" ? " chip-active" : "")}
          onClick={() => {
            setJson(JSON.stringify(rules, null, 2));
            setJsonError(null);
            setMode("json");
          }}
        >
          Raw JSON
        </button>
      </div>

      {mode === "builder" ? (
        <>
          <div className="field">
            <span>Match</span>
            <div className="radio-row">
              <label className="radio">
                <input
                  type="radio"
                  checked={match === "all"}
                  onChange={() => setMatch("all")}
                />
                <span>All rules (AND)</span>
              </label>
              <label className="radio">
                <input
                  type="radio"
                  checked={match === "any"}
                  onChange={() => setMatch("any")}
                />
                <span>Any rule (OR)</span>
              </label>
            </div>
          </div>
          <div className="rule-rows">
            {rows.length === 0 ? (
              <p className="muted small">No rules yet.</p>
            ) : (
              rows.map((r, i) => (
                <div className="rule-row" key={i}>
                  <input
                    placeholder="field (e.g. attributes.plan)"
                    value={r.field}
                    onChange={(e) => updateRow(i, { field: e.target.value })}
                  />
                  <select
                    value={r.op}
                    onChange={(e) => updateRow(i, { op: e.target.value })}
                  >
                    {RULE_OPS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                  <input
                    placeholder="value"
                    value={r.value}
                    onChange={(e) => updateRow(i, { value: e.target.value })}
                    disabled={r.op === "exists"}
                  />
                  <button
                    type="button"
                    className="btn-icon"
                    onClick={() => removeRow(i)}
                    aria-label="Remove rule"
                  >
                    ×
                  </button>
                </div>
              ))
            )}
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={addRow}
          >
            + Add rule
          </button>
        </>
      ) : (
        <label className="field">
          <span>Rules JSON</span>
          <textarea
            className="code"
            rows={8}
            value={json}
            onChange={(e) => applyJson(e.target.value)}
          />
          {jsonError ? (
            <span className="muted small" style={{ color: "var(--danger)" }}>
              {jsonError}
            </span>
          ) : null}
        </label>
      )}
    </div>
  );
}

function stepSummary(step: AutomationStep): string {
  switch (step.type) {
    case "send": {
      const s = step.config.subject;
      return typeof s === "string" && s ? s : "(no subject)";
    }
    case "wait": {
      const d = step.config.delay_days;
      const h = step.config.delay_hours;
      if (typeof d === "number") return `Wait ${d} day(s)`;
      if (typeof h === "number") return `Wait ${h} hour(s)`;
      return "Wait";
    }
    case "condition": {
      const rules =
        step.config.rules && typeof step.config.rules === "object"
          ? (step.config.rules as RulesObject)
          : {};
      const rows = rulesToRows(rules);
      return `${rows.length} rule(s) · ${rulesMatch(rules)}`;
    }
  }
}

// ---------------------------------------------------------------------------
// Enroll modal (manual automations)
// ---------------------------------------------------------------------------

function EnrollModal({
  automationId,
  onClose,
}: {
  automationId: number;
  onClose: () => void;
}) {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [segmentId, setSegmentId] = useState("");
  const [contactIds, setContactIds] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const s = await api.get<Segment[]>("/api/segments");
        setSegments(s);
      } catch (err) {
        setError(errMessage(err));
      }
    })();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    const ids = contactIds
      .split(/[,\s]+/)
      .map((x) => Number(x.trim()))
      .filter((n) => Number.isFinite(n) && n > 0);
    if (!segmentId && ids.length === 0) {
      setError("Pick a segment or enter at least one contact ID.");
      return;
    }
    setBusy(true);
    try {
      const res = await enrollAutomation(automationId, {
        segment_id: segmentId ? Number(segmentId) : undefined,
        contact_ids: ids.length ? ids : undefined,
      });
      setNotice(`Enrolled ${res.enrolled} contact(s).`);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Enroll contacts" onClose={onClose}>
      <ErrorBanner message={error} />
      <SuccessBanner message={notice} />
      <form onSubmit={onSubmit} className="form">
        <label className="field">
          <span>Segment</span>
          <select
            value={segmentId}
            onChange={(e) => setSegmentId(e.target.value)}
          >
            <option value="">— None —</option>
            {segments.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Or contact IDs (comma or space separated)</span>
          <input
            value={contactIds}
            onChange={(e) => setContactIds(e.target.value)}
            placeholder="12, 34, 56"
          />
        </label>
        <div className="actions-row">
          <button className="btn btn-primary" disabled={busy}>
            {busy ? "Enrolling…" : "Enroll"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// AI draft sequence modal
// ---------------------------------------------------------------------------

function AiSequenceModal({
  onClose,
  onApply,
}: {
  onClose: () => void;
  onApply: (steps: AutomationStep[]) => void;
}) {
  const [goal, setGoal] = useState("");
  const [count, setCount] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await draftSequence(goal, count);
      const steps: AutomationStep[] = [];
      res.emails.forEach((email, idx) => {
        steps.push({
          type: "send",
          config: { subject: email.subject, html: email.html },
        });
        // Insert a wait between emails based on the next email's lead time.
        const next = res.emails[idx + 1];
        if (next && next.wait_days > 0) {
          steps.push({ type: "wait", config: { delay_days: next.wait_days } });
        }
      });
      onApply(steps);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setError(AI_DISABLED);
      } else {
        setError(errMessage(err));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="AI: draft sequence" onClose={onClose}>
      <ErrorBanner message={error} />
      <form onSubmit={onSubmit} className="form">
        <label className="field">
          <span>Goal</span>
          <textarea
            rows={3}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Onboard new trial users over their first week"
            required
          />
        </label>
        <label className="field">
          <span>Number of emails</span>
          <input
            type="number"
            min={1}
            max={10}
            value={count}
            onChange={(e) => setCount(Number(e.target.value) || 1)}
          />
        </label>
        <div className="actions-row">
          <button className="btn btn-primary" disabled={busy || !goal.trim()}>
            {busy ? "Drafting…" : "Draft sequence"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Runs panel
// ---------------------------------------------------------------------------

function RunsPanel({ automationId }: { automationId: number }) {
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const r = await getAutomationRuns(automationId);
      setRuns(r);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [automationId]);

  return (
    <Card
      title="Recent runs"
      actions={
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={load}
          disabled={loading}
        >
          Refresh
        </button>
      }
    >
      <ErrorBanner message={error} />
      {loading ? (
        <Spinner label="Loading runs…" />
      ) : runs.length === 0 ? (
        <p className="muted small">No enrolled contacts yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Contact</th>
                <th>Step</th>
                <th>Status</th>
                <th>Next run</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td className="mono">#{r.contact_id}</td>
                  <td className="num">{r.position}</td>
                  <td>
                    <StatusPill status={r.status} />
                    {r.last_error ? (
                      <div className="muted small">{r.last_error}</div>
                    ) : null}
                  </td>
                  <td className="muted small">
                    {r.next_run_at
                      ? new Date(r.next_run_at).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main builder
// ---------------------------------------------------------------------------

export default function AutomationBuilder() {
  const navigate = useNavigate();
  const params = useParams();
  const isNew = !params.id;

  const [loading, setLoading] = useState(!isNew);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [status, setStatus] = useState<Automation["status"]>("draft");

  const [name, setName] = useState("");
  const [triggerType, setTriggerType] = useState<TriggerType>("manual");
  const [triggerListId, setTriggerListId] = useState("");
  const [domainId, setDomainId] = useState("");
  const [fromName, setFromName] = useState("");
  const [fromEmail, setFromEmail] = useState("");
  const [steps, setSteps] = useState<AutomationStep[]>([]);

  const [lists, setLists] = useState<List[]>([]);
  const [domains, setDomains] = useState<SendingDomain[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);

  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showEnroll, setShowEnroll] = useState(false);
  const [showAi, setShowAi] = useState(false);

  function hydrate(a: Automation) {
    setSavedId(a.id);
    setStatus(a.status);
    setName(a.name);
    setTriggerType(a.trigger_type);
    setTriggerListId(a.trigger_list_id ? String(a.trigger_list_id) : "");
    setDomainId(a.sending_domain_id ? String(a.sending_domain_id) : "");
    setFromName(a.from_name ?? "");
    setFromEmail(a.from_email ?? "");
    setSteps(a.steps ?? []);
  }

  useEffect(() => {
    (async () => {
      try {
        const [l, d, t] = await Promise.all([
          api.get<List[]>("/api/lists"),
          api.get<SendingDomain[]>("/api/sending-domains"),
          listTemplates(),
        ]);
        setLists(l);
        setDomains(d);
        setTemplates(t);
      } catch (err) {
        setError(errMessage(err));
      }
    })();
  }, []);

  useEffect(() => {
    if (isNew) return;
    (async () => {
      try {
        const a = await getAutomation(params.id!);
        hydrate(a);
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [isNew, params.id]);

  // ----- step operations -----
  function addStep(type: StepType) {
    setSteps((prev) => [...prev, newStep(type)]);
  }
  function moveStep(from: number, to: number) {
    if (to < 0 || to >= steps.length) return;
    setSteps((prev) => {
      const next = prev.slice();
      const [item] = next.splice(from, 1);
      next.splice(to, 0, item);
      return next;
    });
  }
  function removeStep(index: number) {
    setSteps((prev) => prev.filter((_, i) => i !== index));
  }
  function updateStepConfig(index: number, config: Record<string, unknown>) {
    setSteps((prev) =>
      prev.map((s, i) => (i === index ? { ...s, config } : s)),
    );
  }

  function buildPayload(): AutomationIn {
    return {
      name,
      trigger_type: triggerType,
      trigger_list_id:
        triggerType === "list_subscribe" && triggerListId
          ? Number(triggerListId)
          : null,
      sending_domain_id: domainId ? Number(domainId) : null,
      from_name: fromName,
      from_email: fromEmail,
      steps: steps.map((s, i) => ({ ...s, position: i })),
    };
  }

  async function onSave(e?: FormEvent) {
    e?.preventDefault();
    setError(null);
    setNotice(null);
    setSaving(true);
    try {
      if (savedId !== null) {
        const updated = await updateAutomation(savedId, buildPayload());
        hydrate(updated);
        setNotice("Automation updated.");
      } else {
        const created = await createAutomation(buildPayload());
        hydrate(created);
        setNotice("Automation saved.");
        navigate(`/automations/${created.id}`, { replace: true });
      }
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function onToggleStatus() {
    if (savedId === null) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const updated =
        status === "active"
          ? await pauseAutomation(savedId)
          : await activateAutomation(savedId);
      hydrate(updated);
      setNotice(status === "active" ? "Automation paused." : "Automation activated.");
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div>
        <PageHeader title="Automation builder" />
        <Card>
          <Spinner label="Loading automation…" />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={savedId !== null ? "Edit automation" : "New automation"}
        subtitle="Design a multi-step journey with sends, waits, and conditions."
        actions={
          <div className="actions-row">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate("/automations")}
            >
              Back
            </button>
            {savedId !== null && (
              <>
                <StatusPill status={status} />
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={onToggleStatus}
                >
                  {busy
                    ? "…"
                    : status === "active"
                      ? "Pause"
                      : "Activate"}
                </button>
                {triggerType === "manual" && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setShowEnroll(true)}
                  >
                    Enroll
                  </button>
                )}
              </>
            )}
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving}
              onClick={onSave}
            >
              {saving
                ? "Saving…"
                : savedId !== null
                  ? "Update"
                  : "Save automation"}
            </button>
          </div>
        }
      />
      <ErrorBanner message={error} />
      <SuccessBanner message={notice} />

      <Card title="Settings">
        <div className="form">
          <label className="field">
            <span>Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Trial onboarding"
              required
            />
          </label>
          <div className="field-row">
            <label className="field">
              <span>Trigger</span>
              <select
                value={triggerType}
                onChange={(e) =>
                  setTriggerType(e.target.value as TriggerType)
                }
              >
                <option value="manual">Manual enrollment</option>
                <option value="list_subscribe">When added to a list</option>
              </select>
            </label>
            {triggerType === "list_subscribe" && (
              <label className="field">
                <span>Trigger list</span>
                <select
                  value={triggerListId}
                  onChange={(e) => setTriggerListId(e.target.value)}
                >
                  <option value="">— Pick a list —</option>
                  {lists.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
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
          </div>
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
        </div>
      </Card>

      <Card
        title="Journey steps"
        actions={
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setShowAi(true)}
          >
            AI: draft sequence
          </button>
        }
      >
        {steps.length === 0 ? (
          <div className="empty">
            No steps yet. Add one below or let AI draft a sequence.
          </div>
        ) : (
          <div className="builder-blocks">
            {steps.map((step, i) => (
              <div key={i} className="builder-block">
                <div className="builder-block-head">
                  <span className="block-kind">
                    {i + 1}. {STEP_LABELS[step.type]} —{" "}
                    <span className="muted">{stepSummary(step)}</span>
                  </span>
                  <div className="row-actions">
                    <button
                      type="button"
                      className="btn-icon"
                      title="Move up"
                      disabled={i === 0}
                      onClick={() => moveStep(i, i - 1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="btn-icon"
                      title="Move down"
                      disabled={i === steps.length - 1}
                      onClick={() => moveStep(i, i + 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-danger"
                      title="Delete"
                      onClick={() => removeStep(i)}
                    >
                      ×
                    </button>
                  </div>
                </div>
                {step.type === "send" && (
                  <SendStepEditor
                    config={step.config}
                    templates={templates}
                    onChange={(config) => updateStepConfig(i, config)}
                  />
                )}
                {step.type === "wait" && (
                  <WaitStepEditor
                    config={step.config}
                    onChange={(config) => updateStepConfig(i, config)}
                  />
                )}
                {step.type === "condition" && (
                  <ConditionStepEditor
                    config={step.config}
                    onChange={(config) => updateStepConfig(i, config)}
                  />
                )}
              </div>
            ))}
          </div>
        )}

        <div className="nested-palette mt">
          {STEP_PALETTE.map((p) => (
            <button
              key={p.type}
              type="button"
              className="chip"
              onClick={() => addStep(p.type)}
            >
              + {p.label}
            </button>
          ))}
        </div>
      </Card>

      {savedId !== null && <RunsPanel automationId={savedId} />}

      {showEnroll && savedId !== null && (
        <EnrollModal
          automationId={savedId}
          onClose={() => setShowEnroll(false)}
        />
      )}
      {showAi && (
        <AiSequenceModal
          onClose={() => setShowAi(false)}
          onApply={(newSteps) => setSteps((prev) => [...prev, ...newSteps])}
        />
      )}
    </div>
  );
}
