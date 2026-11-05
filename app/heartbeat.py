"""Ping the client now and then and hang up on connections that went quiet."""
import asyncio
import contextlib
import time

from fastapi import WebSocket

from .config import settings


class Activity:
    """Remembers when we last heard from the client."""

    def __init__(self):
        self.last_seen = time.monotonic()

    def touch(self):
        self.last_seen = time.monotonic()


async def heartbeat(ws: WebSocket, activity: Activity):
    while True:
        await asyncio.sleep(settings.ws_ping_seconds)
        if time.monotonic() - activity.last_seen > settings.ws_idle_timeout_seconds:
            with contextlib.suppress(RuntimeError):
                await ws.close(code=1001, reason="Idle timeout")
            return
        try:
            await ws.send_json({"type": "ping"})
        except (RuntimeError, Exception):
            return  # the connection is gone, nothing left to do
