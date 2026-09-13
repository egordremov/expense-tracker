"""Authentication and request limits run before FastAPI reads request bodies."""
import asyncio
import hmac
import threading
import time
from collections import OrderedDict, deque

from starlette.responses import JSONResponse

import settings as cfg

MAX_REQUEST_BYTES = 64 * 1024
BODY_TIMEOUT_SECONDS = 10


class RateLimiter:
    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def clear(self):
        with self.lock:
            self.entries.clear()

    def allow(self, key, limit, window):
        with self.lock:
            now = time.monotonic()
            queue = self.entries.pop(key, deque())
            while queue and now - queue[0] >= window:
                queue.popleft()
            self.entries[key] = queue
            while len(self.entries) > 1024:
                self.entries.popitem(last=False)
            if len(queue) >= limit:
                return False
            queue.append(now)
            return True


limiter = RateLimiter()


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        protected = path == "/api" or path.startswith("/api/")
        public_live = path == "/api/live" and scope["method"] in ("GET", "HEAD")

        async def secure_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([(b"x-content-type-options", b"nosniff"),
                                (b"x-frame-options", b"DENY"), (b"referrer-policy", b"no-referrer")])
                if protected or path in ("/", "/settings"):
                    headers.append((b"cache-control", b"no-store"))
                message = {**message, "headers": headers}
            await send(message)

        async def reject(status, detail):
            await JSONResponse({"detail": detail}, status_code=status)(scope, receive, secure_send)

        headers = scope.get("headers", [])
        if protected and not public_live:
            if cfg.secrets_broken():
                await reject(503, "Secret storage is unavailable; restore it locally.")
                return
            token = cfg.get("ADMIN_TOKEN")
            if not token:
                await reject(503, "Set ADMIN_TOKEN in the server environment before using the application.")
                return
            supplied = [value for key, value in headers if key == b"x-admin-token"]
            if len(supplied) != 1 or not hmac.compare_digest(supplied[0], token.encode("utf-8")):
                peer = (scope.get("client") or ("unknown",))[0]
                status = 401 if limiter.allow(("auth", peer), 20, 60) else 429
                await reject(status, "Admin token required." if status == 401 else "Too many authentication attempts.")
                return

        lengths = [value for key, value in headers if key == b"content-length"]
        if lengths:
            if len(lengths) != 1 or not lengths[0].isdigit():
                await reject(400, "Invalid Content-Length.")
                return
            if len(lengths[0]) > 10 or int(lengths[0]) > MAX_REQUEST_BYTES:
                await reject(413, "Request body is too large.")
                return
        body = bytearray()
        try:
            async with asyncio.timeout(BODY_TIMEOUT_SECONDS):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > MAX_REQUEST_BYTES:
                        await reject(413, "Request body is too large.")
                        return
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            await reject(408, "Request body timed out.")
            return

        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, secure_send)
