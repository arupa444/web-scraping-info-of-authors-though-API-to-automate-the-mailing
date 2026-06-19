# iceReach Phase 3 (Automation Journeys) Implementation Plan

> Use superpowers:subagent-driven-development / executing-plans. Steps use `- [ ]`.

**Goal:** A working automation engine — enroll contacts on a trigger, then run an ordered journey of **send / wait / condition(filter)** steps with delays — plus AI sequence drafting and a basic builder UI.

**Architecture:** `Automation` has ordered `AutomationStep`s and a trigger. Enrolling a contact creates an `AutomationRun` (cursor at position 0, `next_run_at=now`). A queue handler (`advance_automations`, enqueued on a schedule) advances every due run: `send` mails the contact via the Phase-1 SMTP/DKIM/tracking pipeline (a `Message` linked to the automation), `wait` sets `next_run_at = now + delay` and advances, `condition` evaluates the segment-rule DSL and continues or exits the run. Steps run in a loop per tick until a `wait` or terminal state. Idempotency: one active run per (automation, contact).

**Reference:** spec §12 P3 — "automation engine (triggers/delays/conditions/branches), drip; AI sequence drafting."

---

## Tasks

### Task 1: Models + migration
**Files:** `backend/icereach/models/automation.py`, `models/__init__.py`, `models/sending.py` (Message link); new Alembic revision
- [ ] `Automation` (workspace-scoped: name, status[draft|active|paused], trigger_type[list_subscribe|manual], trigger_list_id?, sending_domain_id?, from_name, from_email).
- [ ] `AutomationStep` (automation_id, position, type[send|wait|condition], config JSON).
- [ ] `AutomationRun` (workspace-scoped: automation_id, contact_id, position, status[active|done|exited|failed], next_run_at, last_error). Unique active run per (automation, contact) enforced in code.
- [ ] `Message`: make `campaign_id` nullable; add nullable `automation_id` FK (so automation emails are tracked too). Update the idempotency note (send pipeline still uses (campaign, contact)).
- [ ] Autogenerate migration; migration roundtrip test includes the 3 new tables.

### Task 2: Engine
**Files:** `backend/icereach/services/automation.py`; Test `backend/tests/test_automation.py`
- [ ] `enroll(db, automation, contact) -> AutomationRun | None` (skip if an active run exists; only when automation active).
- [ ] `enroll_for_list(db, workspace_id, list_id, contact_ids)` — enroll into active automations with `trigger_type=list_subscribe` and matching `trigger_list_id`.
- [ ] `_send_step(db, run, automation, step)` — render subject/html/text (from step config or `template_id`), create `Message(automation_id=...)`, rewrite links + pixel, build w/ List-Unsubscribe, DKIM-sign if verified, send via `SmtpSession`. Reuse `services.merge`, `services.tracking`, `services.smtp`.
- [ ] `advance_run(db, run)` — loop: if `next_run_at>now` stop; execute step at position; `send`→advance+continue; `wait`→`next_run_at=now+delay`, advance, stop; `condition`→`segments.build_filter` match? advance : `status=exited`; position past end→`status=done`. Catch per-run errors → `status=failed`, `last_error`.
- [ ] `advance_due_runs(db, limit=100)` — process all active runs with `next_run_at<=now`.
- [ ] `@register("advance_automations")` queue handler calling `advance_due_runs`.
- [ ] Tests (stub `SmtpSession`): enroll creates a run; a send→wait→send journey advances correctly across two ticks (wait honored via `next_run_at`); condition filter exits a non-matching contact; a `Message` is created with `automation_id`; double-enroll is a no-op.

### Task 3: Router + AI sequence + enrollment hook
**Files:** `backend/icereach/routers/automations.py`, `schemas/automation.py`; modify `routers/lists.py`, `ai/service.py`, `ai/prompts.py`, `routers/ai.py`; Test `backend/tests/test_automations_api.py`
- [ ] CRUD `/api/automations` (with nested steps), `POST /{id}/activate`, `POST /{id}/pause`, `POST /{id}/enroll` (manual: contact_ids or segment_id), `GET /{id}/runs`.
- [ ] `lists.add_contacts` calls `enroll_for_list` after adding memberships.
- [ ] `ai.service.draft_sequence(goal, steps=3) -> list[{subject, html, wait_days}]` + `POST /api/ai/sequence`.
- [ ] Tests (TestClient, stub SMTP + monkeypatch AI): create automation with steps; activate; manual enroll → run created; list→subscribe auto-enrolls; AI sequence endpoint shape (mocked).

### Task 4: SPA UI
**Filesःं** `frontend/src/pages/Automations.tsx`, `AutomationBuilder.tsx`; nav + routes; api.ts types.
- [ ] Automations list; builder (trigger picker, ordered steps add/edit/reorder/delete for send/wait/condition, "AI draft sequence" button), activate/pause, runs view. `npm run build` passes.

## Definition of Done
- `pytest backend/tests -q` green incl. engine + migration roundtrip.
- A list-subscribe enrolls a contact; the worker tick advances send→wait→send with the delay honored; condition exits non-matching contacts; automation emails are tracked Messages.
- SPA builds; can author + activate an automation and see runs.

## Out of scope (later)
Arbitrary multi-branch graphs (use linear + condition-filter now); event/webhook triggers (P5); A/B within journeys (P4).
