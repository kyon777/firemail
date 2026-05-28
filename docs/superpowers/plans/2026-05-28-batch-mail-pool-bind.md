# Batch Mail Pool Bind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a customer-facing batch mailbox binding flow that accepts one email per line, checks the private mail pool through a versioned in-memory cache, and imports matched accounts into the current user's mailbox list.

**Architecture:** Backend adds a `mail_pool_meta` version and a `MailPoolCache` that reloads only when the DB version changes. `POST /api/mail-pool/batch-bind` parses user input, resolves entries via cache, then binds through existing DB ownership rules without exposing the full pool. Frontend adds a modal on `EmailsView` for multiline input and result summary.

**Tech Stack:** Flask, SQLite, Vue 3, Pinia, Element Plus, unittest, Vitest.

---

### Task 1: Backend tests

**Files:**
- Modify: `backend/tests/test_mail_pool.py`

- [x] Add DB tests for `mail_pool_meta` version bump and batch binding statuses.
- [x] Add API test for `POST /api/mail-pool/batch-bind` returning per-line results without exposing tokens.
- [x] Run `python -m unittest backend.tests.test_mail_pool -v` and confirm failures before implementation.

### Task 2: Backend implementation

**Files:**
- Modify: `backend/database/db.py`
- Create: `backend/utils/mail_pool_cache.py`
- Modify: `backend/app.py`

- [x] Add `mail_pool_meta` with `pool_version` and bump on insert/bind status changes.
- [x] Add `MailPoolCache` that reloads `mail_pool` only when `pool_version` differs.
- [x] Add `bind_mail_pool_emails(user_id, emails, resolver)` for per-line binding.
- [x] Add `POST /api/mail-pool/batch-bind` using cache and existing auth.

### Task 3: Frontend tests and UI

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/store/emails.js`
- Modify: `frontend/src/views/EmailsView.vue`
- Modify: `frontend/src/views/__tests__/EmailsView.mailPoolBinding.spec.js`

- [x] Add API/store method `batchBindPoolEmails`.
- [x] Add modal button and textarea in `EmailsView`.
- [x] Show total, bound, already_bound, not_found, assigned_to_other counts and per-line table.
- [x] Run `npm test -- --run`.

### Task 4: Verification and release

- [x] Run backend focused tests.
- [x] Run frontend tests and build.
- [x] Rebuild Docker with `docker compose up --build -d --force-recreate`.
- [x] Verify `http://localhost:18000/api/health` and logs.
- [x] Commit and push master.
