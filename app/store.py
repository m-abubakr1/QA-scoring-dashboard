"""Reading and writing calls. Every function takes a session and returns plain dicts."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import rubric
from .db import Alert, Call, Line, Note, Score, utcnow
from .scoring import ScoreResult


def iso(dt) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def call_dict(c: Call) -> dict:
    return {
        "id": c.id, "agent_name": c.agent_name, "customer_label": c.customer_label, "status": c.status,
        "started_at": iso(c.started_at), "ended_at": iso(c.ended_at), "overall": c.overall,
    }


def line_dict(ln: Line) -> dict:
    return {"seq": ln.seq, "speaker": ln.speaker, "text": ln.text, "at": iso(ln.at)}


def alert_dict(a: Alert) -> dict:
    return {"id": a.id, "call_id": a.call_id, "type": a.type, "severity": a.severity,
            "message": a.message, "created_at": iso(a.created_at)}


def note_dict(n: Note) -> dict:
    return {"id": n.id, "call_id": n.call_id, "author": n.author, "text": n.text, "created_at": iso(n.created_at)}


def score_dict(s: Score) -> dict:
    return {"kind": s.kind, "overall": s.overall, "rubric_version": s.rubric_version,
            "created_at": iso(s.created_at), **s.data}


def create_call(s: Session, agent_name: str, customer_label: str = "Customer", sample_id: str | None = None) -> dict:
    call = Call(agent_name=agent_name, customer_label=customer_label, sample_id=sample_id)
    s.add(call)
    s.flush()
    return call_dict(call)


def get_call(s: Session, call_id: int) -> Call | None:
    return s.get(Call, call_id)


def add_line(s: Session, call_id: int, speaker: str, text: str) -> dict:
    seq = (s.scalar(select(func.count()).select_from(Line).where(Line.call_id == call_id)) or 0) + 1
    line = Line(call_id=call_id, seq=seq, speaker=speaker, text=text)
    s.add(line)
    s.flush()
    return line_dict(line)


def get_lines(s: Session, call_id: int) -> list[dict]:
    rows = s.scalars(select(Line).where(Line.call_id == call_id).order_by(Line.seq))
    return [line_dict(r) for r in rows]


def end_call(s: Session, call_id: int) -> dict:
    call = s.get(Call, call_id)
    call.status, call.ended_at = "ended", utcnow()
    return call_dict(call)


def save_score(s: Session, call_id: int, kind: str, result: ScoreResult) -> dict:
    row = Score(call_id=call_id, kind=kind, overall=result.overall, data=result.to_dict(),
                rubric_version=rubric.VERSION)
    s.add(row)
    if kind == "final":
        s.get(Call, call_id).overall = result.overall
    s.flush()
    return score_dict(row)


def latest_score(s: Session, call_id: int) -> dict | None:
    """The final score if there is one, otherwise the newest live score."""
    rows = list(s.scalars(select(Score).where(Score.call_id == call_id).order_by(Score.id.desc())))
    final = next((r for r in rows if r.kind == "final"), None)
    pick = final or (rows[0] if rows else None)
    return score_dict(pick) if pick else None


def has_alert(s: Session, call_id: int, alert_type: str) -> bool:
    return s.scalar(select(func.count()).select_from(Alert)
                    .where(Alert.call_id == call_id, Alert.type == alert_type)) > 0


def add_alert(s: Session, call_id: int, alert_type: str, severity: str, message: str) -> dict:
    a = Alert(call_id=call_id, type=alert_type, severity=severity, message=message)
    s.add(a)
    s.flush()
    return alert_dict(a)


def add_note(s: Session, call_id: int, author: str, text: str) -> dict:
    n = Note(call_id=call_id, author=author, text=text)
    s.add(n)
    s.flush()
    return note_dict(n)


def call_detail(s: Session, call_id: int) -> dict | None:
    call = s.get(Call, call_id)
    if call is None:
        return None
    alerts = s.scalars(select(Alert).where(Alert.call_id == call_id).order_by(Alert.id))
    notes = s.scalars(select(Note).where(Note.call_id == call_id).order_by(Note.id))
    return {
        **call_dict(call),
        "lines": get_lines(s, call_id),
        "score": latest_score(s, call_id),
        "alerts": [alert_dict(a) for a in alerts],
        "notes": [note_dict(n) for n in notes],
    }


def list_calls(s: Session, agent: str | None = None, status: str | None = None,
               max_overall: float | None = None, limit: int = 50) -> list[dict]:
    q = select(Call).order_by(Call.id.desc()).limit(limit)
    if agent:
        q = q.where(Call.agent_name == agent)
    if status:
        q = q.where(Call.status == status)
    if max_overall is not None:
        q = q.where(Call.overall <= max_overall)
    return [call_dict(c) for c in s.scalars(q)]


def agent_summary(s: Session) -> list[dict]:
    """One row per agent: finished calls, average score and how many calls had a compliance alert."""
    rows = s.execute(
        select(Call.agent_name, func.count(Call.id), func.avg(Call.overall))
        .where(Call.status == "ended").group_by(Call.agent_name).order_by(Call.agent_name)
    ).all()
    flagged = dict(s.execute(
        select(Call.agent_name, func.count(func.distinct(Call.id)))
        .join(Alert, Alert.call_id == Call.id).where(Alert.type == "compliance").group_by(Call.agent_name)
    ).all())
    return [{"agent_name": name, "calls": n, "average": round(avg, 1) if avg is not None else None,
             "compliance_alerts": flagged.get(name, 0)} for name, n, avg in rows]


def add_lines(s: Session, call_id: int, lines: list[dict]) -> list[dict]:
    """Add many lines at once, for transcripts that arrive whole."""
    return [add_line(s, call_id, ln["speaker"], ln["text"]) for ln in lines]
