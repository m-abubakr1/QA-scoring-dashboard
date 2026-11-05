"""The live part: calls come in, get scored as they go, and every supervisor watching hears about it."""
import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass

from fastapi import WebSocket
from starlette.requests import HTTPConnection

from . import store
from .config import settings
from .llm import LLM, LLMError
from .scoring import ScoreResult, score_transcript

log = logging.getLogger("qa")


class CallNotFound(Exception):
    pass


class CallEnded(Exception):
    pass


@dataclass(eq=False)
class Watcher:
    name: str
    ws: WebSocket
    id: str = ""

    def __post_init__(self):
        self.id = uuid.uuid4().hex[:8]

    def public(self) -> dict:
        return {"id": self.id, "name": self.name}


@dataclass
class Runtime:
    """What we track for a call that is in progress."""
    since_score: int = 0  # lines added since the last live score
    running: bool = False  # a live scoring is in flight
    pending: bool = False  # more lines arrived while it was running, so go again
    last_overall: float | None = None


class Monitor:
    def __init__(self, session_factory, llm_provider):
        self.sf = session_factory
        self.get_llm = llm_provider
        self.watchers: dict[str, Watcher] = {}
        self._runtime: dict[int, Runtime] = {}
        self._tasks: set[asyncio.Task] = set()

    # ---- plumbing -------------------------------------------------------

    async def db(self, fn, *args):
        """Run a store function in a thread, so the event loop is never blocked by the database."""
        def run():
            with self.sf() as s:
                out = fn(s, *args)
                s.commit()
                return out
        return await asyncio.to_thread(run)

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self):
        for t in list(self._tasks):
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ---- watchers -------------------------------------------------------

    def roster(self) -> list[dict]:
        return [w.public() for w in self.watchers.values()]

    async def broadcast(self, message: dict, exclude: Watcher | None = None):
        """Send to every supervisor. One slow or dead connection must not stop the rest."""
        async def one(w: Watcher):
            with contextlib.suppress(Exception):
                await w.ws.send_json(message)
        await asyncio.gather(*(one(w) for w in list(self.watchers.values()) if w is not exclude))

    # ---- calls ----------------------------------------------------------

    async def start_call(self, agent_name: str, customer_label: str = "Customer", sample_id: str | None = None) -> dict:
        call = await self.db(store.create_call, agent_name, customer_label, sample_id)
        self._runtime[call["id"]] = Runtime()
        await self.broadcast({"type": "call_started", "call": call})
        return call

    async def _live_call(self, call_id: int):
        row = await self.db(lambda s: (lambda c: c and store.call_dict(c))(store.get_call(s, call_id)))
        if row is None:
            raise CallNotFound(call_id)
        if row["status"] != "live":
            raise CallEnded(call_id)

    async def add_line(self, call_id: int, speaker: str, text: str) -> dict:
        await self._live_call(call_id)
        line = await self.db(store.add_line, call_id, speaker, text)
        await self.broadcast({"type": "line", "call_id": call_id, "line": line})
        rt = self._runtime.setdefault(call_id, Runtime())
        rt.since_score += 1
        if rt.since_score >= settings.score_every_lines:
            rt.since_score = 0
            self._schedule_live_score(call_id)
        return line

    async def end_call(self, call_id: int) -> dict:
        await self._live_call(call_id)
        await self.db(store.end_call, call_id)
        await self._score(call_id, final=True)
        call = await self.db(lambda s: store.call_dict(store.get_call(s, call_id)))
        self._runtime.pop(call_id, None)
        await self.broadcast({"type": "call_ended", "call": call})
        return call

    async def import_call(self, agent_name: str, customer_label: str, lines: list[dict]) -> dict:
        """A transcript that is already finished: store it, score it once, tell the supervisors."""
        call = await self.db(store.create_call, agent_name, customer_label, None)
        await self.db(store.add_lines, call["id"], lines)
        await self.broadcast({"type": "call_started", "call": call})
        await self.db(store.end_call, call["id"])
        await self._score(call["id"], final=True)
        call = await self.db(lambda s: store.call_dict(store.get_call(s, call["id"])))
        self._runtime.pop(call["id"], None)
        await self.broadcast({"type": "call_ended", "call": call})
        return call

    async def add_note(self, call_id: int, author: str, text: str) -> dict:
        exists = await self.db(lambda s: store.get_call(s, call_id) is not None)
        if not exists:
            raise CallNotFound(call_id)
        note = await self.db(store.add_note, call_id, author, text)
        await self.broadcast({"type": "note", "call_id": call_id, "note": note})
        return note

    # ---- scoring --------------------------------------------------------

    def _schedule_live_score(self, call_id: int):
        """Score now, or if one is already running, remember to go once more when it finishes."""
        rt = self._runtime.setdefault(call_id, Runtime())
        if rt.running:
            rt.pending = True
            return
        rt.running = True

        async def loop():
            try:
                while True:
                    rt.pending = False
                    await self._score(call_id, final=False)
                    if not rt.pending:
                        break
            finally:
                rt.running = False

        self.spawn(loop())

    async def _score(self, call_id: int, final: bool) -> ScoreResult | None:
        lines = await self.db(store.get_lines, call_id)
        if len(lines) < 2:
            return None
        try:
            result = await score_transcript(self.get_llm(), lines, complete=final)
        except LLMError as exc:
            log.warning("scoring call %s failed: %s", call_id, exc)
            await self.broadcast({"type": "score_error", "call_id": call_id, "message": str(exc)})
            return None
        saved = await self.db(store.save_score, call_id, "final" if final else "live", result)
        await self._raise_alerts(call_id, result, final)
        await self.broadcast({"type": "score", "call_id": call_id, "kind": saved["kind"], "score": saved})
        return result

    async def _raise_alerts(self, call_id: int, result: ScoreResult, final: bool):
        rt = self._runtime.setdefault(call_id, Runtime())
        found: list[tuple[str, str, str]] = []

        compliance = next((c for c in result.criteria if c.id == "compliance"), None)
        if compliance and compliance.score is not None and compliance.score <= 2:
            if not await self.db(store.has_alert, call_id, "compliance"):
                found.append(("compliance", "high", f"Compliance scored {compliance.score}/5. {compliance.reasoning}"))

        if rt.last_overall is not None and result.overall is not None \
                and rt.last_overall - result.overall >= settings.score_drop_alert:
            found.append(("score_drop", "medium", f"Score fell from {rt.last_overall} to {result.overall}."))

        if final and result.overall is not None and result.overall < settings.low_score_alert:
            if not await self.db(store.has_alert, call_id, "low_score"):
                found.append(("low_score", "medium", f"Final score is {result.overall}, below {settings.low_score_alert}."))

        if result.overall is not None:
            rt.last_overall = result.overall
        for kind, severity, message in found:
            alert = await self.db(store.add_alert, call_id, kind, severity, message)
            await self.broadcast({"type": "alert", "call_id": call_id, "alert": alert})

    # ---- simulator ------------------------------------------------------

    async def simulate(self, sample: dict, speed: float) -> dict:
        """Replay a sample call line by line, like a call happening right now."""
        call = await self.start_call(sample["agent_name"], "Customer", sample["id"])

        async def replay():
            for ln in sample["lines"]:
                await asyncio.sleep(1 / speed)
                await self.add_line(call["id"], ln["speaker"], ln["text"])
            await self.end_call(call["id"])

        self.spawn(replay())
        return call


def get_monitor(conn: HTTPConnection) -> Monitor:
    return conn.app.state.monitor
