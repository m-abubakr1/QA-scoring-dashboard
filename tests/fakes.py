import json

from app import rubric
from app.llm import LLMError


def good_score(evidence_by_id: dict[str, list[str]] | None = None, scores: dict[str, int | None] | None = None) -> str:
    """A model answer in the right shape. Every criterion gets 4 unless scores says otherwise."""
    scores = scores or {}
    evidence_by_id = evidence_by_id or {}
    return json.dumps({
        "criteria": [
            {"id": c.id, "score": scores.get(c.id, 4), "evidence": evidence_by_id.get(c.id, []), "reasoning": "ok"}
            for c in rubric.RUBRIC
        ],
        "summary": "Fine call.",
    })


class FakeLLM:
    """Stands in for the real model. `responder(system, user)` decides what it says."""

    model = "fake-model"

    def __init__(self, responder=None):
        self.responder = responder or (lambda system, user: good_score())
        self.calls: list[str] = []
        self.fail = False

    async def complete(self, system: str, user: str, json_mode: bool = False) -> str:
        self.calls.append(user)
        if self.fail:
            raise LLMError("boom")
        return self.responder(system, user)
