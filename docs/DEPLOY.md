# Deploying on a fresh Linux server

This guide takes an empty Ubuntu/Debian box (VM, VPS or Raspberry Pi) to a running instance of the
mail-receipt expense tracker in about ten minutes. Everything after step 3 is done in the web UI.

## 1. Prerequisites

- Ubuntu 22.04/24.04 or Debian 12, 1 vCPU, 1 GB RAM, ~5 GB disk. x86-64 or arm64 both work.
- Docker Engine + Compose plugin:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"     # log out and back in afterwards
docker compose version               # should print v2.x
```

- An IMAP mailbox that receives the receipts. For Gmail you need an **app password**
  (Google Account → Security → 2-Step Verification → App passwords), not the account password.

## 2. Get the code

```bash
git clone <your-git-remote>/expense-tracker.git ~/expense-tracker
cd ~/expense-tracker
cp .env.example .env               # first installation only
chmod 600 .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

`.env` is a fallback: a variable from it is used only while no value for it has been saved in the web UI.
Set the generated value as `ADMIN_TOKEN` in `.env` before starting. All APIs except `/api/live` require a token.
Preserve an existing token when upgrading; new tokens need at least 32 printable ASCII characters without spaces.

> **Languages:** the web UI is available in Russian, English and Lithuanian (RU / EN / LT selector in the page header;
> the choice is remembered per browser). Item names of Maxima receipts are translated into Russian; in EN/LT the
> original Lithuanian names are shown. Free-form error texts and journal entries written before this feature remain in
> Russian. Button names below are given in English with the Russian label in brackets where it helps.
If you prefer to preconfigure, set at least `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`;
the file is read by the container only, keep it `chmod 600`.

## 3. Start

```bash
mkdir -p data
sudo chown -R 10001:10001 data       # application container UID/GID
sudo chmod 700 data
docker compose up -d --build
docker compose ps                  # expense-tracker: Up (healthy) after ~1 min — the healthcheck only asks whether the app answers
curl -i http://localhost/api/live    # public liveness; /api/health requires X-Admin-Token
```

The container listens on ports **80** and **8080** (both map to the app), restarts automatically
(`restart: always`), rotates its logs (3×10 MB) and stores all data in `./data`:

| Path | What |
|---|---|
| `data/expenses.db` | SQLite: expenses, processed mails, stores, settings, sync journal |
| `data/secrets.json` | IMAP password, Claude key, admin token set via UI (mode 0600) |
| `data/backup/` | daily copies of the DB (14 days) + copies taken before a full rebuild |

Time zone: `TZ=Europe/Vilnius` in `docker-compose.yml` — change it so the daily 08:00 sync
happens in your local morning.

## 4. Configure in the browser

Open `http://<server-ip>/settings`.

1. **Mail (IMAP)** — server, mailbox address, app password. Click *Test connection* («Проверить подключение»):
   it uses the values currently typed into the form and must report the folder it will read (Gmail: "All Mail",
   found automatically in any account language) and the number of mails per store for the last 30 days.
   Then click **Save settings** («Сохранить настройки», the blue button below the Access section) — it saves the
   Mail, Schedule, Claude and Access sections together. Each store row has its own *Save* button.
2. **Stores and senders** — full addresses or domains (`maxima.lt`, `wolt.com, order.site`).
   Matching uses the mailbox domain, including its subdomains, never the display name. Parser:
   - `auto` — tries, in this order: the Maxima receipt format, Wolt/order.site PDF receipts, Claude (if an
     API key is set), and finally a generic search for the receipt total;
   - `maxima` / `wolt` — only that format;
   - `generic` — only the total of the mail, never Claude.
   *Default category for all purchases* is handy for food delivery or utility bills; leave it
   empty to categorise every line item (grocery dictionary, Lithuanian → Russian).
   Mails about one order (confirmation, "ready for pickup", PDF invoice) are merged by order number and
   stable store ID. Independent purchases with equal amounts are not merged. Without an order number,
   do not assume that different messages describe the same purchase.
   **Find in mailbox** scans the last N days and lists senders whose mails look like receipts
   or carry PDF attachments, with a suggested category — *Add* prefills a row.
3. **Schedule and reliability** — daily time (default 08:00), retry interval/count, timeouts,
   alert thresholds (no successful sync for N hours, no new receipts for N days). Clear the daily time
   to use interval scheduling; the empty value is saved explicitly.
4. **Claude (optional)** — API key and model. With a key, receipts of stores without a
   dedicated parser are itemised and item names are translated; without it the app still works.
5. **Access** — rotate the **admin token** when needed. Both pages ask for it. All API routes except
   `/api/live` require authentication, including expense data and sync. The token cannot be cleared.
   Changing the IMAP host, port or user requires entering the mail password again before testing or saving.
6. **Maintenance** → *Synchronise* («Синхронизировать», choose "for a year") to backfill history for newly
   added stores. *Rebuild from mail* («Пересобрать всё из почты») downloads mail for the known history,
   then replaces expenses of *enabled* stores in one transaction after taking a DB backup. Missing known
   message IDs stop the rebuild; `force=yes` allows intentional removal of those messages only. Empty or
   incomplete fetches, folder warnings, parse failures and suspicious totals abort even with force.
   Failed or timed-out rebuilds preserve old expenses. Disabled stores are untouched. Configuration writes
   during any sync return HTTP 409; retry them after it finishes.

The dashboard at `http://<server-ip>/` shows totals, per-store and per-category charts, a daily
or monthly chart and the itemised table; period presets, custom date ranges and store/category
filters are in the top bar.

## 5. Keep it reliable

Already built in: daily sync with retries every 30 min on failure, catch-up sync 30 s after the
container starts, IMAP and whole-sync timeouts, supervision of the background task, per-mail
error isolation with retries from stored text, `/api/health` returning **503** with a list of
`problems` when something needs attention (also shown as a red banner on the dashboard).
Each sync runs in a separate process which is killed and reaped on its deadline. Run exactly one
Uvicorn worker: scheduler ownership and the configuration/sync lock are process-local.
Broken or textless PDFs are shown as unparsed receipts with diagnostics, not silently ignored.

Recommended on the host:

```bash
# autostart Docker on boot
sudo systemctl enable docker

# external liveness monitor: GET /api/live, expect HTTP 200
# detailed health and optional cron sync require X-Admin-Token in a protected client config
```

Optional: `sudo apt-get install -y avahi-daemon libnss-mdns` and `sudo hostnamectl set-hostname receipts`
makes the box reachable as `http://receipts.local` inside the LAN. If you run it in a VM, enable autostart in
your hypervisor.

## 6. Security notes

- Ports 80/8080 are published on all interfaces. Either keep the server inside a trusted LAN,
  restrict with a firewall (`ufw allow from 192.168.0.0/24 to any port 80`), or put a reverse
  proxy with TLS and basic auth in front and change `ports:` to `127.0.0.1:8080:8080`.
- Always set the admin token before first access. A changed IMAP destination requires an explicit password.
  The saved IMAP host is trusted administrator configuration. Limits: 5 connection tests per 10 minutes,
  5 manual syncs per minute, 2 rebuilds per 10 minutes. Invalid secret storage closes API access.
- Authentication precedes JSON parsing. Bodies are limited to 64 KiB and 10 seconds, including chunked requests.
- IMAP TLS verifies the server certificate and hostname using the system trust store. For an internal
  mail server, install its CA into that trust store instead of disabling certificate verification.
- Secrets never appear in API responses; `data/secrets.json` is not included in backups.
- Mail passwords and Claude keys can be cleared; admin tokens cannot. An admin-token `__reset__` requires
  a valid environment token. Secret files have 0600 permissions from creation, before any content is written.
- The container runs as UID/GID 10001 with no capabilities and a read-only root filesystem. Limits:
  1 GiB RAM, one CPU, 64 processes; the Linux sync worker also limits address space to 768 MiB.
- Mail/PDF limits and migration details: [security fixes](SECURITY-FIXES-2026-09-13.md).

## 7. Updating

```bash
cd ~/expense-tracker
git pull
sudo chown -R 10001:10001 data       # required after the former root container
sudo chmod 700 data
docker compose up -d --build       # DB schema migrates automatically on start
curl -s http://localhost/api/live
```

Settings, stores and data live in `./data` and survive rebuilds. To roll back the database,
stop the container and copy a file from `data/backup/` over `data/expenses.db`.
Before major updates, stop the app and make a separate backup of `data/expenses.db` and
`data/secrets.json` (protect the latter as a secret). Startup migrates old order fingerprints to store IDs
and adds missing metadata columns. It does not repair historical duplicate or missing expenses:
review them and explicitly rebuild after taking a backup. Older code does not understand null secret
overrides and may reactivate credentials from the environment when rolled back.
See [the audit](REVIEW-2026-09-12.md) and [test instructions](TESTING.md) before deploying.

## 8. Troubleshooting

| Symptom | Where to look |
|---|---|
| `/api/health` → 503, `problems` says mail not configured / credentials rejected («почта не настроена», «IMAP не принял логин/пароль») | Settings → Mail; Gmail needs an app password; *Test connection* shows the exact server reply |
| "no successful sync for more than 26 h" | `docker compose logs --tail 100`; Settings → Maintenance → sync journal |
| receipts of a store are missing | is the store enabled and does its full sender address/domain match the mailbox in `From`? Use *Find in mailbox*; then *Synchronise for a year* |
| "N receipts could not be parsed" | Settings → Maintenance → *Problem receipts* shows the mail text — the format is unknown; add a Claude key or report the sample |
| duplicate expenses | compare Message-ID and order number; same-order mail is merged by stable store ID and reference, not amount. Correct the parser/reference extraction for an unsupported format, then rebuild explicitly |
| the daily sync didn't happen after a reboot | `docker compose ps` — container should be Up; a catch-up sync runs 30 s after start; check `date` and `TZ` |

## 9. Running without Docker (alternative)

Export `ADMIN_TOKEN` in the shell before running these commands. Uvicorn does not load `.env` automatically;
for a persistent systemd service, use `EnvironmentFile` as shown below. Use Python 3.12 or later.

```bash
sudo apt-get install -y python3-venv
python3 -m venv .venv && . .venv/bin/activate
pip install --require-hashes -r requirements.lock
DB_PATH=$PWD/data/expenses.db TZ=Europe/Vilnius uvicorn main:app --host 0.0.0.0 --port 8080
```

Wrap it in a systemd service with `Restart=always` and `EnvironmentFile=/path/.env`; everything
else (settings UI, backups, health) is identical.
Set OS memory/CPU limits for non-Docker deployment too; the worker address-space limit applies only on Linux.
