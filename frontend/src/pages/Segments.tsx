import { useEffect, useState, type FormEvent } from "react";
import {
  api,
  type Segment,
  type SegmentPreview,
  type SegmentRules,
} from "../lib/api";
import {
  Card,
  Empty,
  ErrorBanner,
  PageHeader,
  Spinner,
  errMessage,
} from "../components/ui";

interface RuleRow {
  field: string;
  op: string;
  value: string;
}

const OPS = [
  { value: "eq", label: "equals" },
  { value: "ne", label: "not equals" },
  { value: "contains", label: "contains" },
  { value: "gt", label: "greater than" },
  { value: "lt", label: "less than" },
  { value: "exists", label: "exists" },
];

function buildRules(match: "all" | "any", rows: RuleRow[]): SegmentRules {
  return {
    match,
    conditions: rows
      .filter((r) => r.field.trim())
      .map((r) => ({ field: r.field.trim(), op: r.op, value: r.value })),
  };
}

export default function Segments() {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // builder
  const [name, setName] = useState("");
  const [mode, setMode] = useState<"builder" | "json">("builder");
  const [match, setMatch] = useState<"all" | "any">("all");
  const [rows, setRows] = useState<RuleRow[]>([{ field: "", op: "eq", value: "" }]);
  const [json, setJson] = useState('{\n  "match": "all",\n  "conditions": []\n}');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // preview
  const [preview, setPreview] = useState<SegmentPreview | null>(null);
  const [previewFor, setPreviewFor] = useState<number | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  async function load() {
    try {
      const s = await api.get<Segment[]>("/api/segments");
      setSegments(s);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function updateRow(i: number, patch: Partial<RuleRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((prev) => [...prev, { field: "", op: "eq", value: "" }]);
  }
  function removeRow(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaveError(null);
    let rules: SegmentRules;
    if (mode === "json") {
      try {
        rules = JSON.parse(json);
      } catch {
        setSaveError("Rules must be valid JSON.");
        return;
      }
    } else {
      rules = buildRules(match, rows);
    }
    setSaving(true);
    try {
      const created = await api.post<Segment>("/api/segments", { name, rules });
      setSegments((prev) => [...prev, created]);
      setName("");
      setRows([{ field: "", op: "eq", value: "" }]);
    } catch (err) {
      setSaveError(errMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function onPreview(id: number) {
    setPreviewError(null);
    setPreview(null);
    setPreviewFor(id);
    setPreviewBusy(true);
    try {
      const p = await api.get<SegmentPreview>(`/api/segments/${id}/preview`);
      setPreview(p);
    } catch (err) {
      setPreviewError(errMessage(err));
    } finally {
      setPreviewBusy(false);
    }
  }

  async function onDelete(id: number) {
    const prev = segments;
    setSegments((s) => s.filter((x) => x.id !== id));
    if (previewFor === id) {
      setPreview(null);
      setPreviewFor(null);
    }
    try {
      await api.del<void>(`/api/segments/${id}`);
    } catch (err) {
      setError(errMessage(err));
      setSegments(prev);
    }
  }

  return (
    <div>
      <PageHeader
        title="Segments"
        subtitle="Dynamic groups defined by contact attributes."
      />
      <ErrorBanner message={error} />

      <Card
        title="Create a segment"
        actions={
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
              onClick={() => setMode("json")}
            >
              Raw JSON
            </button>
          </div>
        }
      >
        <ErrorBanner message={saveError} />
        <form onSubmit={onSave} className="form">
          <label className="field">
            <span>Name</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Active customers in the US"
              required
            />
          </label>

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
                    <span>All conditions (AND)</span>
                  </label>
                  <label className="radio">
                    <input
                      type="radio"
                      checked={match === "any"}
                      onChange={() => setMatch("any")}
                    />
                    <span>Any condition (OR)</span>
                  </label>
                </div>
              </div>

              <div className="rule-rows">
                {rows.map((r, i) => (
                  <div className="rule-row" key={i}>
                    <input
                      className="rule-field"
                      placeholder="field (e.g. country)"
                      value={r.field}
                      onChange={(e) => updateRow(i, { field: e.target.value })}
                    />
                    <select
                      value={r.op}
                      onChange={(e) => updateRow(i, { op: e.target.value })}
                    >
                      {OPS.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                    <input
                      className="rule-value"
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
                      disabled={rows.length === 1}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
              <button type="button" className="btn btn-ghost btn-sm" onClick={addRow}>
                + Add condition
              </button>
            </>
          ) : (
            <label className="field">
              <span>Rules JSON</span>
              <textarea
                className="code"
                rows={8}
                value={json}
                onChange={(e) => setJson(e.target.value)}
              />
            </label>
          )}

          <button className="btn btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save segment"}
          </button>
        </form>
      </Card>

      <Card title="Your segments">
        {loading ? (
          <Spinner />
        ) : segments.length === 0 ? (
          <Empty message="No segments yet." />
        ) : (
          <ul className="simple-list">
            {segments.map((s) => (
              <li key={s.id}>
                <div className="simple-list-main">
                  <strong>{s.name}</strong>
                  <span className="muted mono">
                    {(s.rules?.conditions?.length ?? 0)} condition(s) ·{" "}
                    {s.rules?.match ?? "all"}
                  </span>
                </div>
                <div className="row-actions">
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => onPreview(s.id)}
                  >
                    Preview
                  </button>
                  <button
                    className="btn btn-ghost btn-sm btn-danger"
                    onClick={() => onDelete(s.id)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {previewFor !== null && (
          <div className="preview-box mt">
            <ErrorBanner message={previewError} />
            {previewBusy ? (
              <Spinner label="Computing preview…" />
            ) : preview ? (
              <>
                <div className="preview-count">
                  <strong>{preview.count}</strong> matching contact(s)
                </div>
                {preview.sample.length > 0 && (
                  <ul className="sample-list">
                    {preview.sample.map((email, i) => (
                      <li key={i} className="mono">
                        {email}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : null}
          </div>
        )}
      </Card>
    </div>
  );
}
