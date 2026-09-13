# Developer Notes

These notes describe the internal structure of the mail receipt expense tracker without assuming a
particular deployment environment.

## Modules

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app, scheduler, sync/rebuild API, health endpoint, admin-token checks, and process supervision for long-running sync work. |
| `sync_worker.py` | Isolated sync worker process. The parent exchanges JSON with it, kills it on timeout, and records diagnostics. |
| `settings.py` | Settings precedence: database settings, `data/secrets.json` for secrets, `.env`, then defaults. Also validation and UI descriptions. |
| `security.py` | ASGI authentication before body parsing, request limits, bounded rate limiter and response headers. |
| `mail_rules.py`, `resource_limits.py` | Exact mailbox/domain matching, mail/PDF budgets and Linux worker memory limit. |
| `static/api.js` | Shared authenticated API client for both pages; same-origin requests and coordinated token prompt. |
| `database.py` | SQLAlchemy/SQLite models, schema migration, backup helpers, receipt replacement, rebuild transactions, and sync journal storage. |
| `imap_client.py` | IMAP connection with TLS hostname verification, sender search, message fetch, body extraction, PDF extraction, connection testing, and sender discovery. |
| `expense_parser.py` | Receipt parsing pipeline: cancellation checks, store-specific parsers, optional Claude parsing, generic total detection, receipt references, and category grouping. |
| `translate.py` | Item-name translation cache plus optional Claude translation and grocery dictionary fallback. |
| `static/i18n.js` | RU/EN/LT dictionaries, locale formatting, category display mapping, language persistence, and localized health/sync messages. |
| `static/index.html` | Dashboard: period presets, filters, cards, charts, sortable table, manual sync button, and health banner. |
| `static/settings.html` | Settings UI, store CRUD, mailbox discovery, sync journal, problem receipts, and admin-token prompt. |

## Backend Message Language

Server-authored return messages and exceptions (including `ValueError` and HTTP errors) are in English.
Health and sync responses retain their structured localization codes for the RU/EN/LT interface.
Persisted category keys, receipt contents, translation dictionaries and user-supplied values keep their original language;
existing journal entries are not rewritten. Keep category defaults in named constants, not inline return literals.
`tests/test_backend_language.py` checks source literals and representative API, sync and IMAP responses.

## Sync Flow

1. `run_sync()` holds the in-process lock and starts `sync_worker.py`. A busy sync returns `{"status":"busy"}`; settings and store mutations return HTTP 409 while sync is active.
2. The fetch window is at least `SYNC_WINDOW_DAYS`, expands after downtime, and is capped by `SYNC_WINDOW_MAX_DAYS`.
3. `fetch_recent()` collects messages for enabled stores, including text and PDF-derived text.
4. Rebuild mode downloads the known history of enabled stores, validates completeness, takes a database backup, and replaces parsed expenses in one transaction.
5. Failed mails are retried from stored text without another IMAP fetch. After `MAX_FAILED_ATTEMPTS`, they become visible terminal `failed` problem receipts.
6. New messages are deduplicated by `Message-ID` and receipt fingerprints. Multi-message orders are merged by stable store ID and extracted order/reference number.
7. Sync results are stored in `sync_runs`; structured `details` let the UI localize journal messages.

Run exactly one Uvicorn worker. The scheduler, sync lock, and process ownership are local to one Python process.

## Settings

Plain settings include IMAP host/user/folder/timeouts, sync schedule and retry parameters, stale/no-receipt thresholds,
fetch window limits, parse retry limits, and the Claude model.

Secrets are `IMAP_PASSWORD`, `ANTHROPIC_API_KEY`, and `ADMIN_TOKEN`. They are stored in `data/secrets.json` with
restricted permissions when configured through the UI. API responses expose only whether each secret is set.

`__clear__` disables the mail password or Claude key. Admin tokens cannot be cleared; `__reset__` for an admin
token requires a valid environment token. All API routes except `/api/live` are protected. Invalid secret storage
closes access. IMAP credentials carry an endpoint/user binding to prevent forwarding after a partial settings failure.

## Testing

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.lock
.venv/bin/python -m unittest discover -s tests -t . -v -b
node tests/test_ui.cjs
```

Tests use temporary databases and synthetic mail fixtures. They should not use a real mailbox, production database, or real credentials.

## Known Limits

- One Uvicorn worker only; horizontal scaling needs a shared scheduler/lock.
- SQLite stores amounts as floats.
- Store/category links are partly string-based for historical records.
- Unknown categories are shown as stored if they are not in `CATS_I18N`.
- Without a Claude key, non-Maxima item names remain in the original receipt language.
- There is no built-in notification channel; use `/api/health` with an external monitor.
- `/api/health` requires a token; `/api/live` is public and has no application diagnostics.
- See [security fixes](SECURITY-FIXES-2026-09-13.md) for processing limits and dependency-lock regeneration.
