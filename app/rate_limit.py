"""A small in-memory token bucket, one bucket per client.

Each client starts with `burst` tokens and gets `per_minute` more every minute, up to
`burst`. A request costs one token. This is per process: with several workers or
servers you would keep the buckets in Redis instead.
"""
import math
import time
from collections import Counter
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, Response

from .config import settings


@dataclass
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: float  # seconds until the next request would be allowed


class RateLimiter:
    def __init__(self, per_minute: float, burst: int, clock=time.monotonic):
        self.rate = per_minute / 60.0
        self.burst = burst
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    def check(self, key: str, cost: int = 1) -> Decision:
        now = self.clock()
        tokens, last = self._buckets.get(key, (float(self.burst), now))
        tokens = min(float(self.burst), tokens + (now - last) * self.rate)
        allowed = tokens >= cost
        if allowed:
            tokens -= cost
        retry = 0.0 if allowed else (cost - tokens) / self.rate
        self._buckets[key] = (tokens, now)
        if len(self._buckets) > 10_000:
            self._prune(now)
        return Decision(allowed, self.burst, int(tokens), retry)

    def _prune(self, now: float):
        full_after = self.burst / self.rate
        self._buckets = {k: v for k, v in self._buckets.items() if now - v[1] < full_after}


class ConnectionCounter:
    """Caps how many WebSockets one client can hold open at the same time."""

    def __init__(self, limit: int):
        self.limit = limit
        self._open: Counter[str] = Counter()

    def acquire(self, key: str) -> bool:
        if self._open[key] >= self.limit:
            return False
        self._open[key] += 1
        return True

    def release(self, key: str):
        self._open[key] -= 1
        if self._open[key] <= 0:
            del self._open[key]


limiter = RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_burst)
connections = ConnectionCounter(settings.ws_max_connections_per_ip)


def get_limiter() -> RateLimiter:
    return limiter


def get_connections() -> ConnectionCounter:
    return connections


def client_id(conn) -> str:
    """Who is asking. Behind a proxy, run uvicorn with --proxy-headers so this is the real IP."""
    return conn.client.host if conn.client else "unknown"


def _headers(d: Decision) -> dict[str, str]:
    return {"X-RateLimit-Limit": str(d.limit), "X-RateLimit-Remaining": str(d.remaining)}


async def rate_limit(request: Request, response: Response, lim: RateLimiter = Depends(get_limiter)):
    """Use as a dependency on the endpoints that cost a model call."""
    d = lim.check(client_id(request))
    if not d.allowed:
        wait = max(1, math.ceil(d.retry_after))
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {wait} second{'s' if wait != 1 else ''}.",
            headers={"Retry-After": str(wait), **_headers(d)},
        )
    response.headers.update(_headers(d))
