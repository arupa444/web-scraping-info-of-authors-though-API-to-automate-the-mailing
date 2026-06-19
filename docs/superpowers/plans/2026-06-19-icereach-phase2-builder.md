# iceReach Phase 2 (Email Builder) Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A block-based email builder: a JSON block document renders to client-safe, inline-styled, table-based HTML; templates are a reusable library; a live-preview/render endpoint matches sent output; test sends work.

**Architecture:** A pure `services/blocks.py` renderer turns a list of block dicts into email HTML (600px table layout, inline styles, merge tags preserved verbatim so the send-time renderer fills them). Templates store their `blocks` JSON plus the derived `html`/`text`. The React SPA edits the block document and previews via the render endpoint (fidelity = sent output). Test sends reuse the Phase-1 SMTP/DKIM pipeline for a single address.

**Reference:** spec §12.2 P2 acceptance — "builder exports client-safe inlined HTML; live preview matches sent output; test sends work."

---

## Block schema

`Template.blocks` is `list[Block]`. Each `Block` is `{ "type": ..., ...props }`:

| type | props |
|---|---|
| `heading` | `text`, `level` (1–3), `align` |
| `text` | `html` (inline HTML allowed; merge tags ok), `align` |
| `button` | `text`, `url`, `align`, `bg`, `color` |
| `image` | `src`, `alt`, `href?`, `width?` |
| `divider` | — |
| `spacer` | `height` (px) |
| `columns` | `columns`: `[[Block,...], [Block,...]]` (2 cols) |

Rendered HTML: a full document with a centered 600px `<table>`, each block a `<tr><td>` with inline styles; merge tags (`{name}`) pass through unchanged.

---

## Tasks

### Task 1: Block renderer
**Files:** Create `backend/icereach/services/blocks.py`; Test `backend/tests/test_blocks.py`
- [ ] Implement `render_blocks(blocks: list[dict], *, preheader: str = "") -> str` producing email-safe inlined HTML (table layout, inline styles). Unknown block type → skip (never raise). HTML-escape text-derived attrs except the `text` block's `html`.
- [ ] Implement `blocks_to_text(blocks) -> str` (reuse `merge.html_to_text` on the rendered HTML).
- [ ] Tests: each block type renders expected tags/styles; merge tag `{name}` survives; columns render two cells; unknown type skipped; output contains `<table` and `max-width:600px`.

### Task 2: Template model + migration
**Files:** Modify `backend/icereach/models/sending.py` (add `blocks` JSON to `Template`); Create `backend/icereach/models/sending.py` SavedBlock; new Alembic revision
- [ ] Add `Template.blocks: Mapped[list] = mapped_column(JSON, default=list)`.
- [ ] Add `SavedBlock(workspace-scoped: name, block JSON)` for reusable blocks.
- [ ] `alembic revision --autogenerate -m "phase2 builder"`; migration roundtrip test still green.

### Task 3: Templates router
**Files:** Create `backend/icereach/routers/templates.py`, `backend/icereach/schemas/template.py`; Test `backend/tests/test_templates.py`
- [ ] CRUD `/api/templates` (name, subject, blocks). On save, derive `html = render_blocks(blocks)` and `text = blocks_to_text(blocks)`.
- [ ] `POST /api/templates/render` (blocks → html, for live preview without saving) and `GET /api/templates/{id}/render` (saved).
- [ ] `POST /api/templates/{id}/test-send` `{to_email, sending_domain_id}` — sync endpoint (FastAPI threadpool): render, merge with sample row `{name:"there"}`, `build_message`, DKIM-sign if verified, send one email via `SmtpSession`. Returns `{sent: true}` or error.
- [ ] Saved-blocks CRUD `/api/saved-blocks`.
- [ ] Tests (TestClient, stub `SmtpSession`): create template derives html/text; render endpoint returns html with table; test-send returns sent with stubbed SMTP; tenant-scoped.

### Task 4: Wire campaign compose to templates
**Files:** Modify `backend/icereach/routers/campaigns.py`
- [ ] `CampaignIn` accepts optional `template_id`; if given and no variants, seed one variant from the template's subject/html/text.
- [ ] Test: campaign created from template_id gets a variant.

### Task 5: SPA email builder
**Files:** `frontend/src/pages/Templates.tsx`, `frontend/src/pages/TemplateBuilder.tsx`, builder components; wire into `CampaignNew`.
- [ ] Templates list (create/edit/delete). Builder: block palette (add), drag-reorder, delete, per-block property editor, **live preview** via `POST /api/templates/render` (iframe srcDoc), save, test-send modal.
- [ ] Campaign compose can pick a template to populate the body.
- [ ] `npm run build` passes.

---

## Definition of Done
- `pytest backend/tests -q` green (incl. new block/template tests + migration roundtrip).
- Render endpoint output is the same HTML that gets sent (minus send-time merge/tracking).
- Test send delivers one rendered email (verified with stubbed SMTP in tests; live-smoke optional).
- SPA builds; builder edits → live preview → save → test-send works against the API.

## Out of scope (later phases)
Automation journeys (P3); ESP adapters/A/B (P4); public API/forms (P5); billing (P6). Also: a full WYSIWYG rich-text editor (use simple HTML/textarea for the `text` block now).
