import hmac

from fastapi import Header, HTTPException, Query, WebSocket

from .config import settings


def _allowed(given: str | None) -> bool:
    if not settings.api_key:  # no key configured, the API is open
        return True
    return given is not None and hmac.compare_digest(given, settings.api_key)


def require_api_key(x_api_key: str | None = Header(default=None)):
    if not _allowed(x_api_key):
        raise HTTPException(status_code=401, detail="Missing or wrong API key")


def ws_allowed(ws: WebSocket) -> bool:
    # browsers cannot set headers on a WebSocket, so the key may also come in the query string
    return _allowed(ws.headers.get("x-api-key") or ws.query_params.get("api_key"))
