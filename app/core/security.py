"""API-key authentication for write endpoints, and security response headers.

Keys
----
A key is a random token (`cbe_` + 32 random bytes, URL-safe). The server never
stores keys, only their SHA-256 hashes in APP_API_KEY_HASHES (comma-separated),
so a leaked config or environment dump does not leak usable credentials. Clients
send the key as `X-API-Key: <key>` or `Authorization: Bearer <key>`.

Generate one with `scripts/new-api-key.sh`.

Policy
------
* Reads (GET) are public.
* Writes require a valid key whenever keys are configured.
* Fail closed: in staging and production, writes are rejected if no keys are
  configured at all, so a missing secret can never open the API.
* development / test without keys: writes are open (local convenience).
"""

import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader
from starlette.datastructures import MutableHeaders

from app.core.config import Settings
from app.core.errors import UnauthorizedError

logger = logging.getLogger("app.security")

KEY_PREFIX = "cbe_"
_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Required for POST, PUT, PATCH and DELETE. Generate with scripts/new-api-key.sh.",
)


def hash_key(key: str) -> str:
    """SHA-256 of an API key, the form stored in APP_API_KEY_HASHES.

    A fast hash is deliberate. Slow password hashes (bcrypt, scrypt, Argon2) exist
    because passwords are low-entropy and can be guessed offline. These keys are
    256 random bits from a CSPRNG (scripts/new-api-key.sh), so even a leaked hash
    cannot be brute-forced, as with GitHub's and Stripe's token storage. A slow hash
    would also add tens of milliseconds of CPU to every write, which is a denial-of-
    service lever. Recorded in docs/security/threat-model.md (CodeQL
    py/weak-sensitive-data-hashing: reviewed, accepted).
    """
    return hashlib.sha256(key.encode()).hexdigest()


def _configured_hashes(settings: Settings) -> list[str]:
    return [h.strip().lower() for h in settings.api_key_hashes.split(",") if h.strip()]


def _presented_key(request: Request, header_key: str | None) -> str | None:
    if header_key:
        return header_key
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        return token.strip()
    return None


def require_write_access(
    request: Request, header_key: Annotated[str | None, Depends(_api_key_header)]
) -> None:
    settings: Settings = request.app.state.settings
    hashes = _configured_hashes(settings)
    if not hashes:
        if settings.environment in ("staging", "production"):
            logger.error("write rejected: no API keys configured (fail closed)")
            raise UnauthorizedError("Writes are disabled: no API keys are configured.")
        return  # development / test without keys

    key = _presented_key(request, header_key)
    if not key:
        raise UnauthorizedError("An API key is required for this operation.")
    digest = hash_key(key)
    # Compare against every configured hash in constant time; do not short-circuit.
    matched = False
    for expected in hashes:
        matched |= hmac.compare_digest(digest, expected)
    if not matched:
        logger.warning("write rejected: invalid API key", extra={"key_prefix": key[:8]})
        raise UnauthorizedError("The API key is not valid.")


WriteAccess = Depends(require_write_access)


# --- Security headers ---------------------------------------------------------------------

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
ASGIApp = Callable[[Scope, Callable, Callable], Awaitable[None]]

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
# The API serves JSON only: nothing may load scripts, frames or other resources.
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
# Swagger UI / ReDoc pages load their scripts and styles from a CDN, so they get
# no restrictive CSP (they are disabled in production unless APP_DEBUG=true).
_DOCS_SUFFIXES = ("/docs", "/redoc", "/docs/oauth2-redirect")


class SecurityHeadersMiddleware:
    """Adds defensive headers to every response. HSTS is set by the TLS terminator
    (nginx), which knows whether the client connection is HTTPS."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope.get("path", "").endswith(_DOCS_SUFFIXES)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _BASE_HEADERS.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", _API_CSP)
                headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)
