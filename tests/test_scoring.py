import asyncio
import json

import pytest

from app import rubric
from app.llm import LLMError
from app.scoring import format_transcript, score_transcript
from tests.fakes import FakeLLM, good_score

LINES = [
    {"speaker": "agent", "text": "Thank you for calling Northwind, this is Sam. How can I help?"},
    {"speaker": "customer", "text": "My internet has been down since yesterday."},
    {"speaker": "agent", "text": "I'm sorry about that, I know how frustrating it is."},
]


def run(coro):
    return asyncio.run(coro)


def test_overall_weights_and_leaves_out_criteria_not_seen():
    assert rubric.overall({c.id: 5 for c in rubric.RUBRIC}) == 100.0
    assert rubric.overall({c.id: 1 for c in rubric.RUBRIC}) == 20.0
    assert rubric.overall({"greeting": 5, "empathy": 3, "resolution": None}) == 73.3
    assert rubric.overall({"greeting": None}) is None


def test_score_has_every_criterion_in_rubric_order():
    result = run(score_transcript(FakeLLM(), LINES, complete=True))
    assert [c.id for c in result.criteria] == [c.id for c in rubric.RUBRIC]
    assert result.overall == 80.0 and result.complete


def test_quotes_found_in_the_transcript_are_kept_and_made_up_ones_are_dropped():
    answer = good_score({"greeting": ["this is Sam", "this is Alex from Initech"]})
    result = run(score_transcript(FakeLLM(lambda s, u: answer), LINES, complete=False))
    greeting = result.criteria[0]
    assert greeting.evidence == ["this is Sam"]
    assert greeting.unverified == 1


def test_quote_match_ignores_case_and_spacing():
    answer = good_score({"empathy": ["I'm   SORRY about that"]})
    result = run(score_transcript(FakeLLM(lambda s, u: answer), LINES, complete=False))
    assert result.criteria[1].evidence == ["I'm   SORRY about that"]


def test_a_criterion_not_seen_yet_has_no_score_and_does_not_count():
    answer = good_score(scores={"closing": None, "resolution": None})
    result = run(score_transcript(FakeLLM(lambda s, u: answer), LINES, complete=False))
    assert result.score_of("closing") is None
    assert result.overall == 80.0  # the others are all 4, so nothing is dragged down


def test_missing_criteria_are_filled_in_as_not_seen():
    answer = json.dumps({"criteria": [{"id": "greeting", "score": 5}], "summary": ""})
    result = run(score_transcript(FakeLLM(lambda s, u: answer), LINES, complete=False))
    assert len(result.criteria) == 6 and result.score_of("empathy") is None and result.overall == 100.0


@pytest.mark.parametrize("bad", ["not json", "{}", json.dumps({"criteria": [{"id": "greeting", "score": 9}]})])
def test_bad_model_answers_raise_an_error(bad):
    with pytest.raises(LLMError):
        run(score_transcript(FakeLLM(lambda s, u: bad), LINES, complete=False))


def test_model_failure_is_passed_up():
    llm = FakeLLM()
    llm.fail = True
    with pytest.raises(LLMError):
        run(score_transcript(llm, LINES, complete=True))


def test_transcript_is_sent_as_data_with_speaker_tags():
    llm = FakeLLM()
    run(score_transcript(llm, LINES, complete=False))
    assert llm.calls[0].startswith("TRANSCRIPT (still in progress):\n[agent] Thank you")
    assert format_transcript(LINES).count("\n") == 2
