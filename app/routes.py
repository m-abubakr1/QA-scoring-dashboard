from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import rubric, samples, store
from .auth import require_api_key
from .hub import CallEnded, CallNotFound, Monitor, get_monitor
from .rate_limit import rate_limit
from .transcripts import TranscriptError, parse_transcript

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


class NewCall(BaseModel):
    agent_name: str = Field(min_length=1, max_length=80)
    customer_label: str = Field(default="Customer", min_length=1, max_length=80)


class NewLine(BaseModel):
    speaker: Literal["agent", "customer"]
    text: str = Field(min_length=1, max_length=1000)


class NewTranscript(BaseModel):
    agent_name: str = Field(min_length=1, max_length=80)
    customer_label: str = Field(default="Customer", min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=100_000, description='Lines like "Agent: hello", or JSON')


class Simulate(BaseModel):
    sample_id: str
    speed: float = Field(default=1.5, gt=0, le=50, description="Lines per second")


def _not_found_or_ended(exc: Exception) -> HTTPException:
    if isinstance(exc, CallNotFound):
        return HTTPException(404, "No call with that id")
    return HTTPException(409, "That call has already ended")


@router.post("/calls", status_code=201, dependencies=[Depends(rate_limit)], summary="Start a call")
async def start_call(body: NewCall, monitor: Monitor = Depends(get_monitor)):
    return await monitor.start_call(body.agent_name, body.customer_label)


@router.post("/calls/{call_id}/lines", status_code=201, summary="Add one line of the transcript")
async def add_line(call_id: int, body: NewLine, monitor: Monitor = Depends(get_monitor)):
    try:
        return await monitor.add_line(call_id, body.speaker, body.text)
    except (CallNotFound, CallEnded) as exc:
        raise _not_found_or_ended(exc)


@router.post("/calls/{call_id}/end", summary="End the call and score it")
async def end_call(call_id: int, monitor: Monitor = Depends(get_monitor)):
    try:
        return await monitor.end_call(call_id)
    except (CallNotFound, CallEnded) as exc:
        raise _not_found_or_ended(exc)


@router.get("/calls", summary="List calls, newest first")
async def list_calls(
    agent: str | None = None,
    status: Literal["live", "ended"] | None = None,
    max_score: float | None = Query(default=None, ge=0, le=100, description="Only calls scored at or below this"),
    limit: int = Query(default=50, ge=1, le=200),
    monitor: Monitor = Depends(get_monitor),
):
    return await monitor.db(store.list_calls, agent, status, max_score, limit)


@router.get("/calls/{call_id}", summary="One call with its transcript, score, alerts and notes")
async def get_call(call_id: int, monitor: Monitor = Depends(get_monitor)):
    detail = await monitor.db(store.call_detail, call_id)
    if detail is None:
        raise HTTPException(404, "No call with that id")
    return detail


@router.get("/agents", summary="Average score and flags for each agent")
async def agents(monitor: Monitor = Depends(get_monitor)):
    return await monitor.db(store.agent_summary)


@router.get("/rubric", summary="The rubric calls are scored against")
async def get_rubric():
    return {
        "version": rubric.VERSION,
        "scale": rubric.SCALE,
        "criteria": [{"id": c.id, "name": c.name, "weight": c.weight, "description": c.description,
                      "critical": c.critical} for c in rubric.RUBRIC],
    }


@router.get("/samples", summary="Practice calls the simulator can replay")
async def get_samples():
    return samples.list_samples()


@router.post("/simulate", status_code=201, dependencies=[Depends(rate_limit)], summary="Replay a practice call live")
async def simulate(body: Simulate, monitor: Monitor = Depends(get_monitor)):
    sample = samples.get_sample(body.sample_id)
    if sample is None:
        raise HTTPException(404, "No sample with that id")
    return await monitor.simulate(sample, body.speed)


@router.post("/transcripts", status_code=201, dependencies=[Depends(rate_limit)],
             summary="Score a transcript you already have")
async def score_transcript_text(body: NewTranscript, monitor: Monitor = Depends(get_monitor)):
    try:
        lines = parse_transcript(body.text)
    except TranscriptError as exc:
        raise HTTPException(422, str(exc))
    return await monitor.import_call(body.agent_name, body.customer_label, lines)
