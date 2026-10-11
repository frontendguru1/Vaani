"""Local-only hardening. Vaani has no login (single user, one Mac), so the threat is other
websites open in the same browser reaching http://127.0.0.1:8000:

- DNS rebinding: evil.example re-resolves to 127.0.0.1 and becomes "same-origin" with the
  API. Blocked by refusing any request whose Host isn't localhost/127.0.0.1.
- Cross-site "simple" requests (e.g. an auto-submitted multipart form) skip CORS preflight.
  Blocked by refusing unsafe methods whose Origin (or Sec-Fetch-Site) says cross-site.
- Oversized uploads: refused up front by Content-Length before anything is spooled.
"""

from __future__ import annotations

from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class OriginGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        settings = get_settings()
        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        method = scope["method"]

        if method not in SAFE_METHODS:
            origin = headers.get("origin")
            fetch_site = headers.get("sec-fetch-site")
            if (origin and origin not in settings.allowed_origins) or fetch_site == "cross-site":
                await _reject(
                    scope, receive, send, 403, "Cross-site request refused.", "cross_site"
                )
                return
            length = headers.get("content-length")
            limit = settings.max_upload_mb * 1024 * 1024
            if length is not None and length.isdigit() and int(length) > limit:
                await _reject(
                    scope,
                    receive,
                    send,
                    413,
                    f"Upload too large (max {settings.max_upload_mb} MB).",
                    "too_large",
                )
                return
            if length is None and "multipart/form-data" in headers.get("content-type", ""):
                await _reject(scope, receive, send, 411, "Content-Length required.", "length")
                return
        await self.app(scope, receive, send)


async def _reject(
    scope: Scope, receive: Receive, send: Send, status: int, detail: str, code: str
) -> None:
    await JSONResponse({"detail": detail, "code": code}, status_code=status)(scope, receive, send)


def install(app) -> None:  # noqa: ANN001
    settings = get_settings()
    # Order: Host check runs first (outermost), then the origin/size guard.
    app.add_middleware(OriginGuard)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
