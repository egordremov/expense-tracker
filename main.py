import asyncio
import ipaddress
import json
import os
import socket
import sys
import threading
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import date, datetime, timedelta

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import database as db
import settings as cfg
from expense_parser import parse_expenses, receipt_ref, reset_claude_breaker, suggest_category
from imap_client import IMAPClient
from mail_rules import normalize_sender
from security import SecurityMiddleware, limiter

HERE = os.path.dirname(__file__)
_lock = threading.Lock()
_wake = None      # asyncio.Event: settings changed; the scheduler needs to recalculate the schedule
_state = {"status": "never", "message": "", "trigger": None, "started_at": None, "finished_at": None,
          "next_sync": None, "last_success_at": None, "consecutive_failures": 0, "folder_warning": None, "details": None}


# ============================ synchronization ============================
def _window(days, reset=False):
    """Fetch window in days. Regular sync: at least the requested window and the days since the last email (+3), capped at the maximum;
    an empty database uses the maximum. reprocess covers all history in the database to avoid losing old receipts."""
    days = days or cfg.get_int("SYNC_WINDOW_DAYS")
    wmax = cfg.get_int("SYNC_WINDOW_MAX_DAYS")
    if reset or db.settings_all().get(REPROCESS_MARK):    # incomplete rebuild: fetch the full history
        first = db.first_known_email_date()
        need = (datetime.now() - first).days + 3 if first else 0
        return max(days, wmax, need)
    last = db.last_processed_email_date()
    if last is None:
        return wmax
    return min(max(days, (datetime.now() - last).days + 3), wmax)


def _friendly_imap_error(e):
    err = str(e)
    if "Application-specific password required" in err:
        return ("Gmail requires an app password, not your account password: create one at myaccount.google.com/apppasswords "
                "and save it in settings (Mail > Password)")
    if "Invalid credentials" in err or "AUTHENTICATIONFAILED" in err:
        return "IMAP rejected the credentials: check the user and password in settings"
    if "Name or service not known" in err or "nodename nor servname" in err or "getaddrinfo" in err:
        return f"IMAP server not found: {cfg.get('IMAP_HOST')}"
    return err


_RICHNESS = {"generic": 1, "fallback": 1, "claude": 2, "wolt": 3, "rules": 3}


def _process_mail(mail, store, counters):
    """Parse and save one email. Exceptions propagate (the email goes into failed_emails).
    Multiple emails for one order (confirmation, ready for pickup, PDF invoice) are merged by order number:
    the record with the most detailed parse is kept."""
    expenses, mode = parse_expenses(mail, store)
    fingerprint = None
    replaces_uid = None
    if expenses:
        ref = receipt_ref(mail)
        if ref:
            fingerprint = db.order_fingerprint(store.id, ref)
            old = db.processed_by_fingerprint(fingerprint)
            if old and old.uid != mail["uid"]:
                if _RICHNESS.get(mode, 0) > _RICHNESS.get(old.parse_mode, 0):
                    replaces_uid = old.uid
                else:
                    db.store_email_expenses(mail, [], "duplicate")
                    counters["dup"] += 1
                    return
        elif not mail.get("has_message_id") and db.fingerprint_exists(db.receipt_fingerprint(mail, expenses)):
            db.store_email_expenses(mail, [], "duplicate")
            counters["dup"] += 1
            return
    db.store_email_expenses(mail, expenses, mode, fingerprint, replaces_uid=replaces_uid)
    counters[mode] = counters.get(mode, 0) + 1
    if replaces_uid:
        counters["superseded"] = counters.get("superseded", 0) + 1
    if mail.get("_suspicious"):
        counters["suspicious"] += 1
    counters["new_mails"] += 1
    counters["new_expenses"] += len(expenses)
    if expenses:
        counters["per_store_new"][store.name] = counters["per_store_new"].get(store.name, 0) + 1


def _give_up_or_retry(mail, error, counters, max_attempts):
    attempts = db.failed_record(mail, error)
    if attempts >= max_attempts:
        db.store_email_expenses(mail, [], "failed")      # terminal state: visible in health and the problem receipts list
        db.failed_delete(mail["uid"])
        counters["gave_up"] += 1
    else:
        counters["failed"] += 1
    print(f"sync: could not process email {mail.get('uid')} ({mail.get('store')}), attempt {attempts}: {error!r}")


def _safe_give_up(mail, error, counters, max_attempts):
    try:
        _give_up_or_retry(mail, error, counters, max_attempts)
    except Exception as e2:                                  # recording an error must not fail the entire batch
        counters["failed"] += 1
        print(f"sync: could not save email {mail.get('uid')} to failed_emails: {e2!r} (original error {error!r})")


REPROCESS_MARK = "_REPROCESS_PENDING"


def _process_batch(mails, skipped, stores, max_attempts):
    by_name = {s.name: s for s in stores}
    c = {"new_mails": 0, "new_expenses": 0, "failed": skipped, "gave_up": 0, "dup": 0, "suspicious": 0,
         "retried_ok": 0, "pending": 0, "per_store_new": {}}
    for fe in db.failed_list():
        mail = fe.as_mail()
        store = by_name.get(fe.store)
        if store is None or not store.enabled:
            continue
        try:
            _process_mail(mail, store, c)
            db.failed_delete(mail["uid"])
            c["retried_ok"] += 1
        except Exception as e:
            _safe_give_up(mail, e, c, max_attempts)
    still_failed = {fe.uid for fe in db.failed_list()}
    for mail in mails:
        if mail["uid"] in still_failed:
            continue
        try:
            if db.is_processed(mail["uid"], mail.get("imap_uid")):
                continue
            c["pending"] += 1
            _process_mail(mail, by_name[mail["store"]], c)
        except Exception as e:
            _safe_give_up(mail, e, c, max_attempts)
    return c


def sync(days=None, trigger="manual", reset=False, force=False):
    """Sync body for a separate process. The rebuild is committed in full after successful parsing."""
    if not _lock.acquire(blocking=False):
        return {"status": "busy", "message": "Synchronisation is already running"}
    started = datetime.now()
    try:
        _state.update(status="running", trigger=trigger, started_at=started.isoformat(timespec="seconds"))
        reset_claude_breaker()
        client = IMAPClient()
        if not client.configured():
            return _finish(started, "error", trigger, "Mail is not configured: enter the IMAP user and password in settings")
        stores = db.stores_list(enabled_only=True)
        if not stores:
            return _finish(started, "error", trigger, "No enabled stores; add a store in settings")
        days = _window(days, reset)
        try:
            mails, skipped, info = client.fetch_recent(days, stores)
        except Exception as e:
            friendly = _friendly_imap_error(e)
            return _finish(started, "error", trigger, friendly if friendly != str(e) else f"IMAP: {friendly}")
        _state["folder_warning"] = info.get("warning")
        max_attempts = cfg.get_int("MAX_FAILED_ATTEMPTS")
        if reset:
            names = [st.name for st in stores]
            if info.get("warning") or skipped or not mails:
                return _finish(started, "error", trigger, "Rebuild cancelled: mail fetch was empty or incomplete; database unchanged")
            missing = db.missing_known_emails(mails, names, datetime.now() - timedelta(days=days))
            if missing and not force:
                return _finish(started, "error", trigger,
                               f"Rebuild cancelled: {len(missing)} previously processed emails are missing; database unchanged (use force=yes for intentional history reduction)")
            try:
                with db.rebuild_expenses(names):
                    c = _process_batch(mails, skipped, stores, max_attempts)
                    if c["failed"] or c["gave_up"] or c.get("unparsed") or c["suspicious"]:
                        raise ValueError("Errors or unparsed receipts remain")
            except Exception as e:
                return _finish(started, "error", trigger, f"Rebuild cancelled; previous expenses preserved: {e}")
        else:
            c = _process_batch(mails, skipped, stores, max_attempts)
        per_store = ", ".join(f"{k}: {v}" for k, v in sorted(info.get("per_store", {}).items(), key=lambda kv: -kv[1]))
        msg = f"Emails in {days} days: {len(mails)}" + (f" ({per_store})" if per_store else "") + \
              f", new: {c['new_mails']}, expenses added: {c['new_expenses']}"
        if c["per_store_new"]:
            msg += " (" + ", ".join(f"{k}: {v}" for k, v in c["per_store_new"].items()) + ")"
        if info.get("folder") and info["folder"] != "INBOX":
            msg += f"; folder {info['folder']}"
        if info.get("warning"):
            msg += f"; {info['warning']}"
        if c["retried_ok"]:
            msg += f"; previously failed emails recovered: {c['retried_ok']}"
        if c["dup"]:
            msg += f"; emails for already recorded orders: {c['dup']}"
        if c.get("superseded"):
            msg += f"; updated from more detailed emails: {c['superseded']}"
        if c.get("unparsed"):
            msg += f"; unparsed receipts: {c['unparsed']}"
        if c["suspicious"]:
            msg += f"; receipts with mismatched totals: {c['suspicious']}"
        if c["failed"]:
            msg += f"; failed: {c['failed']} (will retry on the next sync)"
        if c["gave_up"]:
            msg += f"; deferred after {max_attempts} failures: {c['gave_up']}"
        if c["failed"] and c["new_mails"] == 0 and (c["pending"] or skipped):
            status = "error"
        elif c["failed"] or c["gave_up"]:
            status = "partial"
        else:
            status = "success"
        if status == "success":
            db.settings_delete(REPROCESS_MARK)               # a complete pass through the full history succeeded
        details = {"days": days, "mails": len(mails), "per_store": info.get("per_store", {}), "new_mails": c["new_mails"],
                   "new_expenses": c["new_expenses"], "per_store_new": c["per_store_new"], "folder": info.get("folder"),
                   "warning": info.get("warning"), "retried_ok": c["retried_ok"], "dup": c["dup"], "superseded": c.get("superseded", 0),
                   "unparsed": c.get("unparsed", 0), "suspicious": c["suspicious"], "failed": c["failed"], "gave_up": c["gave_up"],
                   "max_attempts": max_attempts}
        return _finish(started, status, trigger, msg, len(mails), c["new_mails"], c["failed"] + c["gave_up"], details)
    except Exception as e:
        return _finish(started, "error", trigger, f"Internal sync error: {e!r}")
    finally:
        _lock.release()


def _finish(started, status, trigger, message, mails=0, new=0, failed=0, details=None):
    now = datetime.now()
    try:
        db.record_sync_run(started, status, trigger, message, mails, new, failed, details)
    except Exception as e:
        print(f"record_sync_run failed: {e!r}")
    _state.update(status=status, message=message, finished_at=now.isoformat(timespec="seconds"), details=details)
    if status in ("success", "partial"):
        _state.update(last_success_at=now.isoformat(timespec="seconds"), consecutive_failures=0)
        try:
            db.backup_db()
        except Exception as e:
            print(f"backup failed: {e!r}")
    else:
        _state["consecutive_failures"] += 1
    print(f"sync[{trigger}] {status}: {message}")
    return dict(_state)


# ============================ scheduler ============================
async def _stop_worker(process):
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.kill()
    await process.wait()


async def run_sync(days=None, trigger="manual", reset=False, force=False):
    """All HTTP/background runs: a separate process, an overall deadline, and guaranteed lock release."""
    if not _lock.acquire(blocking=False):
        return {"status": "busy", "message": "Synchronisation is already running"}
    started = datetime.now()
    process = None
    try:
        _state.update(status="running", trigger=trigger, started_at=started.isoformat(timespec="seconds"), details=None)
        request = {"days": days, "trigger": trigger, "reset": reset, "force": force, "state": dict(_state)}
        timeout = cfg.get_int("SYNC_TIMEOUT_MINUTES") * 60
        process = await asyncio.create_subprocess_exec(
            sys.executable, os.path.join(HERE, "sync_worker.py"),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            env={**os.environ, "DB_PATH": db.DB_PATH}, cwd=HERE)
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(json.dumps(request).encode()), timeout=timeout)
        except asyncio.TimeoutError:
            await _stop_worker(process)
            return _finish(started, "error", trigger, f"Sync stopped after a {timeout / 60:g}-minute timeout")
        if process.returncode != 0:
            raise RuntimeError(f"Sync process exited with code {process.returncode}")
        result = json.loads(stdout)
        if result.get("status") not in ("success", "partial", "error"):
            raise RuntimeError("Invalid result from the sync process")
        _state.update({k: v for k, v in result.items() if k != "next_sync"})
        return dict(_state)
    except asyncio.CancelledError:
        if process:
            await _stop_worker(process)
        _finish(started, "error", trigger, "Sync stopped during application shutdown")
        raise
    except Exception as e:
        return _finish(started, "error", trigger, f"Sync process error: {e}")
    finally:
        try:
            if process and process.returncode is None:
                await _stop_worker(process)
        finally:
            _lock.release()


async def _safe_sync(trigger):
    """-> status of this run. Wait up to 20 minutes for a busy lock (manual sync/rebuild), then treat the attempt as failed."""
    for _ in range(80):
        res = await run_sync(trigger=trigger)
        if res.get("status") != "busy":
            return res.get("status")
        await asyncio.sleep(15)
    db.record_sync_run(datetime.now(), "error", trigger, "Run skipped: another sync or rebuild has been running for 20 minutes")
    return "error"


async def _sleep(seconds):
    """Sleep interrupted by settings changes. -> True if woken up."""
    try:
        await asyncio.wait_for(_wake.wait(), timeout=max(1.0, seconds))
        _wake.clear()
        return True
    except asyncio.TimeoutError:
        return False


async def _sync_with_retries(trigger):
    status = await _safe_sync(trigger)
    retries = 0
    while status == "error" and retries < cfg.get_int("SYNC_RETRY_MAX"):
        retries += 1
        every = cfg.get_int("SYNC_RETRY_MINUTES") * 60
        _state["next_sync"] = (datetime.now() + timedelta(seconds=every)).isoformat(timespec="minutes") + " (retry)"
        if await _sleep(every):
            continue
        status = await _safe_sync("retry")


def _seconds_until_daily(hhmm):
    hh, mm = (int(x) for x in hhmm.split(":"))
    now = datetime.now()
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    _state["next_sync"] = nxt.isoformat(timespec="minutes")
    return (nxt - now).total_seconds()


async def _periodic():
    await asyncio.sleep(30)
    await _sync_with_retries("startup")
    while True:
        try:
            daily = cfg.get_time("SYNC_DAILY_AT")
            if daily:
                secs = _seconds_until_daily(daily)
            else:
                secs = cfg.get_int("SYNC_INTERVAL_MINUTES") * 60
                _state["next_sync"] = (datetime.now() + timedelta(seconds=secs)).isoformat(timespec="minutes")
            if await _sleep(secs):
                continue                          # settings changed: recalculate the schedule
            await _sync_with_retries("schedule")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"scheduler loop error: {e!r}")
            await asyncio.sleep(60)


def _spawn_scheduler(app):
    task = asyncio.create_task(_periodic())

    def _done(t):
        if t.cancelled():
            return
        print(f"Scheduler task died: {t.exception()!r}; restarting")
        _spawn_scheduler(app)

    task.add_done_callback(_done)
    app.state.scheduler = task


@asynccontextmanager
async def lifespan(app):
    global _wake
    os.umask(0o077)
    _wake = asyncio.Event()
    db.init_db()
    cfg.invalidate()
    ls = db.last_success_at()
    _state["last_success_at"] = ls.isoformat(timespec="seconds") if ls else None
    _spawn_scheduler(app)
    try:
        yield
    finally:
        app.state.scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await app.state.scheduler


app = FastAPI(title="Expenses from email", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityMiddleware)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


@app.get("/api/live")
def live():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/settings")
def settings_page():
    return FileResponse(os.path.join(HERE, "static", "settings.html"))


# ============================ health / journal ============================
_PROBLEM_EN = {
    "imap_not_configured": "Mail is not configured (IMAP user/password)",
    "no_success_yet": "No successful sync yet",
    "stale": "No successful sync for more than {hours} hours",
    "last_error": "Last sync failed: {message}",
    "folder_warning": "{text}",
    "secrets_broken": "Cannot read data/secrets.json; API access and stored credentials are unavailable",
    "reprocess_pending": "Database rebuild is incomplete; history will be recovered during subsequent syncs",
    "no_stores": "No enabled stores",
    "unparsed": "{n} receipts from the last 30 days could not be parsed; see Problem receipts in settings",
    "failed": "{n} emails from the last 30 days were deferred after repeated parsing failures",
    "failed_pending": "{n} emails are waiting to be parsed again",
    "no_receipts": "No new receipts for {days} days (last: {last}); check whether emails stopped arriving or went to spam",
    "db_error": "Database unavailable: {error}",
}


def _health_payload():
    """problems contains English text; problems_i18n contains codes and parameters for UI localization."""
    imap_ok = bool(cfg.get("IMAP_USER") and cfg.get("IMAP_PASSWORD"))
    ls = _state["last_success_at"]
    stale_h = cfg.get_int("STALE_AFTER_HOURS")
    codes = []

    def add(code, **params):
        codes.append({"code": code, "params": params})

    if not imap_ok:
        add("imap_not_configured")
    elif ls is None:
        add("no_success_yet")
    elif datetime.now() - datetime.fromisoformat(ls) > timedelta(hours=stale_h):
        add("stale", hours=stale_h)
    if _state["status"] in ("error", "partial"):
        add("last_error", message=_state["message"])
    if _state.get("folder_warning"):
        add("folder_warning", text=_state["folder_warning"])
    if cfg.secrets_broken():
        add("secrets_broken")
    try:
        if db.settings_all().get(REPROCESS_MARK):
            add("reprocess_pending")
        if not db.stores_list(enabled_only=True):
            add("no_stores")
        for store in db.stores_list(enabled_only=True):
            try:
                for sender in store.sender_list():
                    normalize_sender(sender)
            except ValueError:
                add("folder_warning", text=f"{store.name}: specify a full sender domain or address in settings")
        pc = db.problem_count(30)
        if pc.get("unparsed"):
            add("unparsed", n=pc["unparsed"])
        if pc.get("failed"):
            add("failed", n=pc["failed"])
        fc = db.failed_count()
        if fc:
            add("failed_pending", n=fc)
        lr = db.last_receipt_date()
        alert_days = cfg.get_int("NO_RECEIPTS_ALERT_DAYS")
        if lr and datetime.now() - lr > timedelta(days=alert_days):
            add("no_receipts", days=(datetime.now() - lr).days, last=f"{lr:%d.%m.%Y}")
    except Exception as e:
        add("db_error", error=repr(e))
    problems = [_PROBLEM_EN[c["code"]].format(**c["params"]) for c in codes]
    daily = cfg.get_time("SYNC_DAILY_AT")
    every = cfg.get_int("SYNC_INTERVAL_MINUTES")
    return {"ok": not problems, "problems": problems, "problems_i18n": codes, "imap_configured": imap_ok,
            "claude_configured": bool(cfg.get("ANTHROPIC_API_KEY")), "admin_token_set": bool(cfg.get("ADMIN_TOKEN")),
            "schedule": f"Daily at {daily}" if daily else f"Every {every} minutes",
            "schedule_i18n": {"daily": daily} if daily else {"every": every},
            "last_sync": dict(_state)}


@app.get("/api/health")
def health():
    payload = _health_payload()
    return JSONResponse(payload, status_code=200 if payload["ok"] else 503)


@app.get("/api/runs")
def runs(limit: int = 30):
    return db.recent_runs(min(max(limit, 1), 200))


# ============================ data ============================
def _resolve_range(days, from_, to):
    try:
        start = date.fromisoformat(from_) if from_ else None
        end = date.fromisoformat(to) if to else None
    except ValueError:
        raise HTTPException(400, "from/to must use YYYY-MM-DD format")
    if start and end and start > end:
        start, end = end, start
    if not start and not end and days:
        end = date.today()
        start = end - timedelta(days=days - 1)
    return start, end


@app.get("/api/expenses")
def expenses(days: int = 0, from_: str | None = Query(None, alias="from"), to: str | None = None, store: str = ""):
    return db.get_all_expenses(*_resolve_range(days, from_, to), store=store or None)


@app.get("/api/categories")
def categories(days: int = 0, from_: str | None = Query(None, alias="from"), to: str | None = None, store: str = ""):
    return db.get_by_category(*_resolve_range(days, from_, to), store=store or None)


@app.get("/api/stats")
def stats(days: int = 0, from_: str | None = Query(None, alias="from"), to: str | None = None, store: str = ""):
    """Period: from/to (inclusive) or a trailing window of `days` days; no parameters means all time. store filters by store."""
    return db.get_stats(*_resolve_range(days, from_, to), store=store or None)


@app.get("/api/stores")
def stores_public():
    return [s.as_dict() for s in db.stores_list()]


@app.post("/api/sync")
async def api_sync(days: int = Query(0, ge=0, le=3650)):
    if not _lock.locked():
        _rate_limit("sync", 5, 60)
    res = await run_sync(days or None, "manual")
    return JSONResponse(res, status_code=409 if res.get("status") == "busy" else 200)


# ============================ administration ============================
@app.get("/api/settings")
def settings_get():
    return {"settings": cfg.describe(), "secrets_path": cfg.SECRETS_PATH, "env_file_hint": "Values from .env apply until overridden here"}


@app.put("/api/settings")
async def settings_put(values: dict = Body(...)):
    try:
        with _configuration_write():
            cfg.set_many(values)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if _wake:
        _wake.set()
    return {"ok": True, "settings": cfg.describe()}


_KNOWN_IMAP = {"imap.gmail.com", "outlook.office365.com", "imap-mail.outlook.com", "imap.mail.yahoo.com", "imap.yandex.com",
               "imap.yandex.ru", "imap.mail.ru", "imap.inbox.lt", "mail.inbox.lt", "imap.fastmail.com", "imap.protonmail.ch",
               "imap.zoho.com", "imap.gmx.net", "imap.mail.me.com", "imap.aol.com", "imap.one.com"}


def _rate_limit(key, limit, window_s):
    if not limiter.allow(("operation", key), limit, window_s):
        raise HTTPException(429, "Too many requests; wait a few minutes")


def _host_allowed(host):
    """Without a token, test-imap with an arbitrary host can be used to guess others' passwords and probe the internal network.
    Allowed: the saved host, known mail providers, public addresses; private/loopback addresses only if they match the saved host."""
    h = host.split(":")[0].lower()
    if h == (cfg.get("IMAP_HOST") or "").split(":")[0].lower() or h in _KNOWN_IMAP:
        return True
    try:
        infos = socket.getaddrinfo(h, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


@app.post("/api/settings/test-imap")
async def settings_test_imap(values: dict = Body(default={})):
    """Test mail access using the supplied (not yet saved) values or the saved values."""
    _rate_limit("test-imap", 5, 600)
    allowed = {"IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD", "IMAP_FOLDER"}
    if any(k not in allowed or not isinstance(v, str) for k, v in values.items()):
        raise HTTPException(400, "IMAP parameters must be strings")
    try:
        for key in ("IMAP_HOST", "IMAP_USER", "IMAP_FOLDER"):
            if key in values:
                cfg.validate(key, values[key])
    except ValueError as e:
        raise HTTPException(400, str(e))
    host = (values.get("IMAP_HOST") or "").strip() or None
    user = (values.get("IMAP_USER") or "").strip() or None
    password = values.get("IMAP_PASSWORD") or None
    changed_identity = cfg.imap_endpoint(host or cfg.get("IMAP_HOST")) != cfg.imap_endpoint(cfg.get("IMAP_HOST")) or (user or cfg.get("IMAP_USER")) != cfg.get("IMAP_USER")
    if changed_identity and (not password or password in ("__clear__", "__reset__")):
        raise HTTPException(400, "Re-enter the password when changing the IMAP server, port or user")
    if password and (len(password) > 4096 or not password.strip()):
        raise HTTPException(400, "Invalid IMAP password")
    if host and not _host_allowed(host):
        raise HTTPException(400, f"Host {host!r} is not allowed for testing; use a known mail provider or save it in settings with the admin token")
    folder = values.get("IMAP_FOLDER") if "IMAP_FOLDER" in values else None
    client = IMAPClient(host=host, user=user, password=password, folder=folder)
    if not client.configured():
        raise HTTPException(400, "User or password is missing")
    try:
        return await asyncio.wait_for(asyncio.to_thread(client.test_connection, db.stores_list(enabled_only=True), 30), timeout=90)
    except asyncio.TimeoutError:
        raise HTTPException(504, "IMAP did not respond within 90 seconds")
    except Exception as e:
        raise HTTPException(400, _friendly_imap_error(e))


@contextmanager
def _configuration_write():
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "Synchronisation is running; change settings after it finishes")
    try:
        yield
    finally:
        _lock.release()


@app.post("/api/stores")
def store_create(data: dict = Body(...)):
    try:
        with _configuration_write():
            return db.store_save(data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/stores/{store_id}")
def store_update(store_id: int, data: dict = Body(...)):
    try:
        with _configuration_write():
            return db.store_save(data, store_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/stores/{store_id}")
def store_remove(store_id: int):
    try:
        with _configuration_write():
            if not db.store_delete(store_id):
                raise HTTPException(404, "Store not found")
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/discover")
async def discover(days: int = 90):
    """Scan mail: senders with receipt-like subjects or PDFs are store candidates."""
    _rate_limit("discover", 2, 600)
    client = IMAPClient()
    if not client.configured():
        raise HTTPException(400, "Mail is not configured")
    try:
        res = await asyncio.wait_for(asyncio.to_thread(client.discover_senders, min(max(days, 7), 365)), timeout=300)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Mailbox scan exceeded 5 minutes; reduce the date range")
    except Exception as e:
        raise HTTPException(400, _friendly_imap_error(e))
    known = {p for s in db.stores_list() for p in s.sender_list()}
    for c in res["candidates"]:
        c["suggested_category"] = suggest_category(c["sender"] + " " + c["name"])
        c["already"] = any(k in c["sender"] or c["sender"] in k for k in known)
    return res


@app.get("/api/receipts/problems")
def receipts_problems(days: int = 30):
    return db.problem_receipts(min(max(days, 1), 400))


@app.post("/api/reprocess")
async def api_reprocess(days: int = Query(0, ge=0, le=3650), confirm: str = "", force: str = ""):
    """Rebuild expenses from mail (after changing the parser/stores). Requires confirm=yes.
    The database is cleared only after a complete fetch; a backup is made before clearing it."""
    if confirm != "yes":
        raise HTTPException(400, "This will replace all parsed expenses for enabled stores by rebuilding from mail. Add ?confirm=yes")
    if not _lock.locked():
        _rate_limit("reprocess", 2, 600)
    res = await run_sync(days or None, "reprocess", True, force == "yes")
    return JSONResponse(res, status_code=409 if res.get("status") == "busy" else 200)
