"""Practice calls the simulator can replay. They are made up, no real customer data."""
import json
from functools import lru_cache
from pathlib import Path

SAMPLES_FILE = Path(__file__).parent.parent / "data" / "sample_calls.json"


@lru_cache
def _load() -> list[dict]:
    return json.loads(SAMPLES_FILE.read_text(encoding="utf-8")) if SAMPLES_FILE.exists() else []


def list_samples() -> list[dict]:
    return [{"id": s["id"], "title": s["title"], "agent_name": s["agent_name"], "lines": len(s["lines"])}
            for s in _load()]


def get_sample(sample_id: str) -> dict | None:
    return next((s for s in _load() if s["id"] == sample_id), None)
