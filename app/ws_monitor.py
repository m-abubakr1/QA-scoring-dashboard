"""WebSocket for supervisors: /ws/monitor?name=Sam

Server sends:
    {"type": "joined", "you": {...}, "watchers": [...], "calls": [...recent calls...]}
    {"type": "presence", "event": "join" | "leave", "watcher": {...}, "watchers": [...]}
    {"type": "call_started", "call": {...}}
    {"type": "line", "call_id": 3, "line": {...}}
    {"type": "score", "call_id": 3, "kind": "live" | "final", "score": {...}}
    {"type": "alert", "call_id": 3, "alert": {...}}
    {"type": "call_ended", "call": {...}}
    {"type": "note", "call_id": 3, "note": {...}}
    {"type": "score_error", "call_id": 3, "message": "..."}
    {"type": "rate_limited", "retry_after": 4.2}   {"type": "error", "message": "..."}   {"type": "ping"}

Client sends:
    {"type": "note", "call_id": 3, "text": "Check this one with the team lead"}
    {"type": "pong"}
"""
import asyncio
import contextlib

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from . import store
from .auth import ws_allowed
from .heartbeat import Activity, heartbeat
from .hub import CallNotFound, Monitor, Watcher, get_monitor, log
from .rate_limit import ConnectionCounter, RateLimiter, client_id, get_connections, get_limiter

router = APIRouter()


@router.websocket("/ws/monitor")
async def monitor_socket(
    ws: WebSocket,
    name: str | None = Query(default=None, max_length=30),
    monitor: Monitor = Depends(get_monitor),
    limiter: RateLimiter = Depends(get_limiter),
    conns: ConnectionCounter = Depends(get_connections),
):
    if not ws_allowed(ws):
        await ws.close(code=1008, reason="Missing or wrong API key")
        return
    who = client_id(ws)
    if not conns.acquire(who):
        await ws.close(code=1013, reason="Too many connections from your address")
        return
    await ws.accept()

    me = Watcher(name=(name or "").strip() or "supervisor", ws=ws)
    monitor.watchers[me.id] = me
    activity = Activity()
    beat = asyncio.create_task(heartbeat(ws, activity))

    async def reply(**message):
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await ws.send_json(message)

    calls = await monitor.db(store.list_calls, None, None, None, 30)
    await reply(type="joined", you=me.public(), watchers=monitor.roster(), calls=calls)
    await monitor.broadcast(
        {"type": "presence", "event": "join", "watcher": me.public(), "watchers": monitor.roster()}, exclude=me
    )

    try:
        while True:
            try:
                data = await ws.receive_json()
            except ValueError:
                await reply(type="error", message="Messages must be valid JSON")
                continue
            activity.touch()
            if not isinstance(data, dict):
                await reply(type="error", message="Messages must be JSON objects")
                continue

            kind = data.get("type")
            if kind == "pong":
                continue
            if kind == "note":
                call_id, text = data.get("call_id"), data.get("text")
                if not isinstance(call_id, int) or not isinstance(text, str) or not 1 <= len(text.strip()) <= 500:
                    await reply(type="error", message="A note needs a call_id and text of 1 to 500 characters")
                    continue
                decision = limiter.check(who)
                if not decision.allowed:
                    await reply(type="rate_limited", retry_after=round(decision.retry_after, 1))
                    continue
                try:
                    await monitor.add_note(call_id, me.name, text.strip())
                except CallNotFound:
                    await reply(type="error", message="No call with that id")
                except Exception:  # a database problem must not close this supervisor's connection
                    log.exception("could not save a note")
                    await reply(type="error", message="Could not save the note, try again")
            else:
                await reply(type="error", message=f"Unknown message type: {kind!r}")
    except WebSocketDisconnect:
        pass
    finally:
        beat.cancel()
        conns.release(who)

        async def cleanup():
            monitor.watchers.pop(me.id, None)
            await monitor.broadcast({"type": "presence", "event": "leave", "watcher": me.public(),
                                     "watchers": monitor.roster()})

        # shielded: the others still hear about it if this handler is cancelled mid-way
        await asyncio.shield(asyncio.create_task(cleanup()))
