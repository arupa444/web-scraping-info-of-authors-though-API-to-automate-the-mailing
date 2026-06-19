import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  createTemplate,
  getTemplate,
  renderBlocks,
  testSendTemplate,
  updateTemplate,
  type Block,
  type BlockAlign,
  type BlockType,
  type ButtonBlock,
  type ColumnsBlock,
  type HeadingBlock,
  type ImageBlock,
  type SendingDomain,
  type SpacerBlock,
  type TextBlock,
  api,
} from "../lib/api";
import {
  Card,
  ErrorBanner,
  Modal,
  PageHeader,
  Spinner,
  SuccessBanner,
  errMessage,
} from "../components/ui";

// ---------------------------------------------------------------------------
// Block factory + metadata
// ---------------------------------------------------------------------------

const PALETTE: { type: BlockType; label: string }[] = [
  { type: "heading", label: "Heading" },
  { type: "text", label: "Text" },
  { type: "button", label: "Button" },
  { type: "image", label: "Image" },
  { type: "divider", label: "Divider" },
  { type: "spacer", label: "Spacer" },
  { type: "columns", label: "Two columns" },
];

const BLOCK_LABELS: Record<BlockType, string> = {
  heading: "Heading",
  text: "Text",
  button: "Button",
  image: "Image",
  divider: "Divider",
  spacer: "Spacer",
  columns: "Two columns",
};

function newBlock(type: BlockType): Block {
  switch (type) {
    case "heading":
      return { type: "heading", text: "Heading text", level: 2, align: "left" };
    case "text":
      return { type: "text", html: "<p>Write something…</p>", align: "left" };
    case "button":
      return {
        type: "button",
        text: "Click here",
        url: "https://example.com",
        align: "center",
      };
    case "image":
      return { type: "image", src: "", alt: "", width: 600 };
    case "divider":
      return { type: "divider" };
    case "spacer":
      return { type: "spacer", height: 24 };
    case "columns":
      return { type: "columns", columns: [[], []] };
  }
}

const ALIGNS: BlockAlign[] = ["left", "center", "right"];

// ---------------------------------------------------------------------------
// Property editor (one per block, recursive for columns)
// ---------------------------------------------------------------------------

function AlignField({
  value,
  onChange,
}: {
  value: BlockAlign | undefined;
  onChange: (v: BlockAlign) => void;
}) {
  return (
    <label className="field">
      <span>Align</span>
      <select
        value={value ?? "left"}
        onChange={(e) => onChange(e.target.value as BlockAlign)}
      >
        {ALIGNS.map((a) => (
          <option key={a} value={a}>
            {a}
          </option>
        ))}
      </select>
    </label>
  );
}

function BlockEditor({
  block,
  onChange,
  nested = false,
}: {
  block: Block;
  onChange: (next: Block) => void;
  nested?: boolean;
}) {
  switch (block.type) {
    case "heading": {
      const b = block as HeadingBlock;
      return (
        <div className="form">
          <label className="field">
            <span>Text</span>
            <input
              value={b.text}
              onChange={(e) => onChange({ ...b, text: e.target.value })}
            />
          </label>
          <div className="field-row">
            <label className="field">
              <span>Level</span>
              <select
                value={b.level}
                onChange={(e) =>
                  onChange({ ...b, level: Number(e.target.value) as 1 | 2 | 3 })
                }
              >
                <option value={1}>H1</option>
                <option value={2}>H2</option>
                <option value={3}>H3</option>
              </select>
            </label>
            <AlignField
              value={b.align}
              onChange={(align) => onChange({ ...b, align })}
            />
          </div>
        </div>
      );
    }
    case "text": {
      const b = block as TextBlock;
      return (
        <div className="form">
          <label className="field">
            <span>HTML</span>
            <textarea
              className="code"
              rows={nested ? 3 : 5}
              value={b.html}
              onChange={(e) => onChange({ ...b, html: e.target.value })}
            />
          </label>
          <AlignField
            value={b.align}
            onChange={(align) => onChange({ ...b, align })}
          />
        </div>
      );
    }
    case "button": {
      const b = block as ButtonBlock;
      return (
        <div className="form">
          <div className="field-row">
            <label className="field">
              <span>Text</span>
              <input
                value={b.text}
                onChange={(e) => onChange({ ...b, text: e.target.value })}
              />
            </label>
            <label className="field">
              <span>URL</span>
              <input
                value={b.url}
                onChange={(e) => onChange({ ...b, url: e.target.value })}
                placeholder="https://…"
              />
            </label>
          </div>
          <div className="field-row">
            <AlignField
              value={b.align}
              onChange={(align) => onChange({ ...b, align })}
            />
            <label className="field">
              <span>Background</span>
              <input
                type="text"
                value={b.bg ?? ""}
                onChange={(e) =>
                  onChange({ ...b, bg: e.target.value || undefined })
                }
                placeholder="#2563eb"
              />
            </label>
          </div>
          <label className="field">
            <span>Text color</span>
            <input
              type="text"
              value={b.color ?? ""}
              onChange={(e) =>
                onChange({ ...b, color: e.target.value || undefined })
              }
              placeholder="#ffffff"
            />
          </label>
        </div>
      );
    }
    case "image": {
      const b = block as ImageBlock;
      return (
        <div className="form">
          <label className="field">
            <span>Source URL</span>
            <input
              value={b.src}
              onChange={(e) => onChange({ ...b, src: e.target.value })}
              placeholder="https://…/image.png"
            />
          </label>
          <div className="field-row">
            <label className="field">
              <span>Alt text</span>
              <input
                value={b.alt ?? ""}
                onChange={(e) =>
                  onChange({ ...b, alt: e.target.value || undefined })
                }
              />
            </label>
            <label className="field">
              <span>Width (px)</span>
              <input
                type="number"
                value={b.width ?? ""}
                onChange={(e) =>
                  onChange({
                    ...b,
                    width: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
              />
            </label>
          </div>
          <label className="field">
            <span>Link URL (optional)</span>
            <input
              value={b.href ?? ""}
              onChange={(e) =>
                onChange({ ...b, href: e.target.value || undefined })
              }
              placeholder="https://…"
            />
          </label>
        </div>
      );
    }
    case "spacer": {
      const b = block as SpacerBlock;
      return (
        <div className="form">
          <label className="field">
            <span>Height (px)</span>
            <input
              type="number"
              value={b.height}
              onChange={(e) =>
                onChange({ ...b, height: Number(e.target.value) || 0 })
              }
            />
          </label>
        </div>
      );
    }
    case "divider":
      return <p className="muted small">No options for this block.</p>;
    case "columns": {
      const b = block as ColumnsBlock;
      const setColumn = (idx: 0 | 1, blocks: Block[]) => {
        const cols: [Block[], Block[]] =
          idx === 0 ? [blocks, b.columns[1]] : [b.columns[0], blocks];
        onChange({ ...b, columns: cols });
      };
      return (
        <div className="builder-columns">
          {([0, 1] as const).map((idx) => (
            <div key={idx} className="builder-column">
              <div className="builder-column-head">Column {idx + 1}</div>
              <NestedBlockList
                blocks={b.columns[idx]}
                onChange={(blocks) => setColumn(idx, blocks)}
              />
            </div>
          ))}
        </div>
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Block row controls (move/duplicate/delete) shared by top + nested lists
// ---------------------------------------------------------------------------

function BlockControls({
  index,
  count,
  onMove,
  onDuplicate,
  onDelete,
}: {
  index: number;
  count: number;
  onMove: (from: number, to: number) => void;
  onDuplicate: (index: number) => void;
  onDelete: (index: number) => void;
}) {
  return (
    <div className="row-actions">
      <button
        type="button"
        className="btn-icon"
        title="Move up"
        disabled={index === 0}
        onClick={() => onMove(index, index - 1)}
      >
        ↑
      </button>
      <button
        type="button"
        className="btn-icon"
        title="Move down"
        disabled={index === count - 1}
        onClick={() => onMove(index, index + 1)}
      >
        ↓
      </button>
      <button
        type="button"
        className="btn-icon"
        title="Duplicate"
        onClick={() => onDuplicate(index)}
      >
        ⧉
      </button>
      <button
        type="button"
        className="btn-icon btn-danger"
        title="Delete"
        onClick={() => onDelete(index)}
      >
        ×
      </button>
    </div>
  );
}

function useBlockOps(blocks: Block[], onChange: (next: Block[]) => void) {
  const move = (from: number, to: number) => {
    if (to < 0 || to >= blocks.length) return;
    const next = blocks.slice();
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };
  const duplicate = (index: number) => {
    const next = blocks.slice();
    next.splice(index + 1, 0, structuredClone(blocks[index]));
    onChange(next);
  };
  const remove = (index: number) => {
    onChange(blocks.filter((_, i) => i !== index));
  };
  const update = (index: number, value: Block) => {
    onChange(blocks.map((b, i) => (i === index ? value : b)));
  };
  return { move, duplicate, remove, update };
}

// Simplified nested editor used inside columns.
function NestedBlockList({
  blocks,
  onChange,
}: {
  blocks: Block[];
  onChange: (next: Block[]) => void;
}) {
  const { move, duplicate, remove, update } = useBlockOps(blocks, onChange);

  return (
    <div className="nested-block-list">
      {blocks.length === 0 ? (
        <p className="muted small">Empty column.</p>
      ) : (
        blocks.map((block, i) => (
          <div key={i} className="nested-block">
            <div className="nested-block-head">
              <span className="block-kind">{BLOCK_LABELS[block.type]}</span>
              <BlockControls
                index={i}
                count={blocks.length}
                onMove={move}
                onDuplicate={duplicate}
                onDelete={remove}
              />
            </div>
            <BlockEditor
              block={block}
              nested
              onChange={(next) => update(i, next)}
            />
          </div>
        ))
      )}
      <div className="nested-palette">
        {PALETTE.filter((p) => p.type !== "columns").map((p) => (
          <button
            key={p.type}
            type="button"
            className="chip"
            onClick={() => onChange([...blocks, newBlock(p.type)])}
          >
            + {p.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Test-send modal
// ---------------------------------------------------------------------------

function TestSendModal({
  templateId,
  defaultSubject,
  onClose,
}: {
  templateId: number;
  defaultSubject: string;
  onClose: () => void;
}) {
  const [domains, setDomains] = useState<SendingDomain[]>([]);
  const [domainId, setDomainId] = useState("");
  const [toEmail, setToEmail] = useState("");
  const [subject, setSubject] = useState(defaultSubject);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const d = await api.get<SendingDomain[]>("/api/sending-domains");
        setDomains(d);
        if (d.length) setDomainId(String(d[0].id));
      } catch (err) {
        setError(errMessage(err));
      }
    })();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await testSendTemplate(templateId, {
        to_email: toEmail,
        sending_domain_id: Number(domainId),
        subject: subject || undefined,
      });
      setNotice(`Test email sent to ${toEmail}.`);
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Send test email" onClose={onClose}>
      <ErrorBanner message={error} />
      <SuccessBanner message={notice} />
      <form onSubmit={onSubmit} className="form">
        <label className="field">
          <span>Recipient email</span>
          <input
            type="email"
            value={toEmail}
            onChange={(e) => setToEmail(e.target.value)}
            placeholder="you@example.com"
            required
          />
        </label>
        <label className="field">
          <span>Sending domain</span>
          <select
            value={domainId}
            onChange={(e) => setDomainId(e.target.value)}
            required
          >
            <option value="">— Pick a domain —</option>
            {domains.map((d) => (
              <option key={d.id} value={d.id}>
                {d.domain}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Subject (optional)</span>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Overrides the template subject"
          />
        </label>
        <div className="actions-row">
          <button
            className="btn btn-primary"
            disabled={busy || !domainId || !toEmail}
          >
            {busy ? "Sending…" : "Send test"}
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
// Live preview (debounced render call)
// ---------------------------------------------------------------------------

function LivePreview({
  blocks,
  preheader,
}: {
  blocks: Block[];
  preheader: string;
}) {
  const [html, setHtml] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const handle = window.setTimeout(async () => {
      setBusy(true);
      setError(null);
      try {
        const res = await renderBlocks({
          blocks,
          preheader: preheader || undefined,
        });
        if (!cancelled) setHtml(res.html);
      } catch (err) {
        if (!cancelled) setError(errMessage(err));
      } finally {
        if (!cancelled) setBusy(false);
      }
    }, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [blocks, preheader]);

  return (
    <div className="preview-pane">
      <div className="preview-pane-head">
        <span className="card-title">Live preview</span>
        {busy ? <span className="muted small">Rendering…</span> : null}
      </div>
      <ErrorBanner message={error} />
      <iframe
        className="preview-frame"
        title="Email preview"
        srcDoc={html}
        sandbox=""
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main builder
// ---------------------------------------------------------------------------

export default function TemplateBuilder() {
  const navigate = useNavigate();
  const params = useParams();
  const isNew = !params.id;
  const templateId = params.id;

  const [loading, setLoading] = useState(!isNew);
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [preheader, setPreheader] = useState("");
  const [blocks, setBlocks] = useState<Block[]>([]);

  const [savedId, setSavedId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showTestSend, setShowTestSend] = useState(false);

  const dragIndex = useRef<number | null>(null);

  useEffect(() => {
    if (isNew) return;
    (async () => {
      try {
        const t = await getTemplate(templateId!);
        setName(t.name);
        setSubject(t.subject);
        setBlocks(t.blocks ?? []);
        setSavedId(t.id);
      } catch (err) {
        setError(errMessage(err));
      } finally {
        setLoading(false);
      }
    })();
  }, [isNew, templateId]);

  const { move, duplicate, remove, update } = useBlockOps(blocks, setBlocks);

  function addBlock(type: BlockType) {
    setBlocks((prev) => [...prev, newBlock(type)]);
  }

  // HTML5 drag reordering for the top-level list.
  function onDragStart(index: number) {
    dragIndex.current = index;
  }
  function onDrop(index: number) {
    const from = dragIndex.current;
    dragIndex.current = null;
    if (from === null || from === index) return;
    move(from, index);
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setSaving(true);
    try {
      const payload = {
        name,
        subject,
        blocks,
        preheader: preheader || undefined,
      };
      if (savedId !== null) {
        const updated = await updateTemplate(savedId, payload);
        setNotice("Template updated.");
        setName(updated.name);
        setSubject(updated.subject);
      } else {
        const created = await createTemplate(payload);
        setSavedId(created.id);
        setNotice("Template saved.");
        navigate(`/templates/${created.id}`, { replace: true });
      }
    } catch (err) {
      setError(errMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const canTestSend = savedId !== null;

  const previewBlocks = useMemo(() => blocks, [blocks]);

  if (loading) {
    return (
      <div>
        <PageHeader title="Template builder" />
        <Card>
          <Spinner label="Loading template…" />
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={savedId !== null ? "Edit template" : "New template"}
        subtitle="Compose your email from blocks and preview it live."
        actions={
          <div className="actions-row">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate("/templates")}
            >
              Back
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!canTestSend}
              onClick={() => setShowTestSend(true)}
              title={canTestSend ? "Send a test email" : "Save the template first"}
            >
              Send test
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={saving}
              onClick={onSave}
            >
              {saving
                ? "Saving…"
                : savedId !== null
                  ? "Update template"
                  : "Save template"}
            </button>
          </div>
        }
      />
      <ErrorBanner message={error} />
      <SuccessBanner message={notice} />

      <Card>
        <div className="form">
          <div className="field-row">
            <label className="field">
              <span>Template name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Welcome email"
                required
              />
            </label>
            <label className="field">
              <span>Subject</span>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Your subject line"
              />
            </label>
          </div>
          <label className="field">
            <span>Preheader (optional)</span>
            <input
              value={preheader}
              onChange={(e) => setPreheader(e.target.value)}
              placeholder="Preview text shown in the inbox"
            />
          </label>
        </div>
      </Card>

      <div className="builder-grid">
        <aside className="builder-palette">
          <div className="card-title">Add block</div>
          <div className="palette-list">
            {PALETTE.map((p) => (
              <button
                key={p.type}
                type="button"
                className="palette-item"
                onClick={() => addBlock(p.type)}
              >
                + {p.label}
              </button>
            ))}
          </div>
        </aside>

        <div className="builder-blocks">
          {blocks.length === 0 ? (
            <div className="empty">
              No blocks yet. Add one from the palette.
            </div>
          ) : (
            blocks.map((block, i) => (
              <div
                key={i}
                className="builder-block"
                draggable
                onDragStart={() => onDragStart(i)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(i)}
              >
                <div className="builder-block-head">
                  <span className="block-kind" title="Drag to reorder">
                    ⠿ {BLOCK_LABELS[block.type]}
                  </span>
                  <BlockControls
                    index={i}
                    count={blocks.length}
                    onMove={move}
                    onDuplicate={duplicate}
                    onDelete={remove}
                  />
                </div>
                <BlockEditor
                  block={block}
                  onChange={(next) => update(i, next)}
                />
              </div>
            ))
          )}
        </div>

        <LivePreview blocks={previewBlocks} preheader={preheader} />
      </div>

      {showTestSend && savedId !== null && (
        <TestSendModal
          templateId={savedId}
          defaultSubject={subject}
          onClose={() => setShowTestSend(false)}
        />
      )}
    </div>
  );
}
