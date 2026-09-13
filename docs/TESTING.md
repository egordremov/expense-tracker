# Testing

Everything here runs offline against temporary SQLite databases with IMAP replaced by fakes.
Never point the tests at the production database (`data/expenses.db`) or at a real mailbox.

## Setup

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
```

Node ≥ 18 is needed for the UI check (no npm packages).

## Run

```bash
python -m unittest discover -s tests -t . -v -b
node tests/test_ui.cjs                             # script syntax, i18n key parity, localization helpers
```

`-b` buffers stdout, so the sync log lines printed by the app do not clutter the output.

## What is covered

| File | Covers |
|---|---|
| `tests/test_settings.py` | precedence DB → secrets.json → .env → defaults; validation; `__clear__` (null override blocks the environment value) vs `__reset__`; broken `secrets.json` blocks writes; explicit empty `SYNC_DAILY_AT` |
| `tests/test_migrations.py` | `init_db()` on databases of older versions: added columns, `store` backfill, order-fingerprint migration to store ids |
| `tests/test_receipts.py` | parsers on synthetic receipts: Maxima line items and total reconciliation, Wolt/order.site PDF text, generic total search, promo/cancellation/refund filtering, amounts with thousands separators, broken PDF → `unparsed` |
| `tests/test_imap.py` | folder discovery by `\All`, mUTF-7 folder names, `UID SEARCH` failure raises, sender→store matching, PDF/HTML body extraction |
| `tests/test_sync.py` | full `sync()` with a fake IMAP: dedup by Message-ID, order merging and supersede in one transaction, failed-mail retries and give-up, rebuild (`reset=True`) refusing on missing known mails / empty fetch / parse errors, rollback on failure, subprocess `run_sync` timeout and lock release |
| `tests/test_api.py` | HTTP layer with `TestClient`: health codes (`problems_i18n`), admin token, 409 during sync, stores CRUD, `test-imap` host allow-list and rate limit, `reprocess` guard |
| `tests/test_backend_language.py` | English validation, health, settings, sync/journal and IMAP messages; no Cyrillic literals in Python `return` or `raise` statements |
| `tests/test_security.py` | Anonymous access denial, closed access on bad secrets, token rotation, IMAP password binding, early JSON limits including chunked/slow requests, rate limiting and file permissions |
| `tests/test_security_mail.py` | Sender spoofing, bounded IMAP fetch, oversized mail diagnostics, mail/PDF budgets and Linux worker limit configuration |
| `tests/test_ui.cjs` | all `<script>` blocks parse; every `data-i18n*` key exists in ru/en/lt; `catName`/`catKey`, `healthProblems`, `syncMessage` |

`tests/support.py` builds an isolated environment per test (temporary `DB_PATH`, defaults in `os.environ`, patched `IMAPClient`) and resets `main._state`.
It also resets rate limits and supplies a synthetic admin token. Browser API helper behavior is covered by `tests/test_ui.cjs`.

## Not covered (verify manually)

- Real IMAP servers and real PDFs — take samples with a script inside the container (`docker compose exec -T expense-tracker python -`), keep them out of the repository.
- Browser rendering — open `/` and `/settings` in each language (RU / EN / LT), check the console for errors, the charts, filters and the settings forms.
- Scheduler timing (08:00 run, retries) — watch `/api/runs` and `/api/health` on the deployed instance.

## Adding a test

Put synthetic mails in `tests/fixtures/` (no personal data), subclass `support.DatabaseTestCase`, and drive `main.sync()` or the
`TestClient`. A regression test should reproduce the bug first (red), then pass with the fix.
