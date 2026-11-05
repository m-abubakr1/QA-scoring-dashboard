import pytest

from app.transcripts import TranscriptError, parse_transcript

TEXT = "Agent: Thanks for calling, this is Sam.\nCustomer: My bill is wrong.\nAgent: Let me look."


def test_parses_labelled_text():
    assert parse_transcript(TEXT) == [
        {"speaker": "agent", "text": "Thanks for calling, this is Sam."},
        {"speaker": "customer", "text": "My bill is wrong."},
        {"speaker": "agent", "text": "Let me look."},
    ]


@pytest.mark.parametrize("line", ["[agent] hi there", "AGENT - hi there", "Rep: hi there", "agent:   hi there  "])
def test_label_styles_and_names(line):
    out = parse_transcript(line + "\nCaller: hello")
    assert out == [{"speaker": "agent", "text": "hi there"}, {"speaker": "customer", "text": "hello"}]


def test_unlabelled_lines_continue_the_previous_speaker_and_blank_lines_are_skipped():
    out = parse_transcript("Agent: First part\n\nand the second part\nCustomer: ok")
    assert out[0]["text"] == "First part and the second part" and len(out) == 2


def test_a_colon_inside_a_sentence_is_not_a_label():
    out = parse_transcript("Agent: Note: it takes 5 days\nCustomer: Fine: thanks")
    assert [o["text"] for o in out] == ["Note: it takes 5 days", "Fine: thanks"]


def test_parses_json_in_both_shapes():
    rows = [{"speaker": "Agent", "text": "hi"}, {"speaker": "customer", "text": "yo"}]
    import json
    assert parse_transcript(json.dumps(rows)) == parse_transcript(json.dumps({"lines": rows}))


@pytest.mark.parametrize("bad, message", [
    ("hello\nbye", "start with"),
    ("Agent: only one line", "at least 2"),
    ('[{"speaker": "bot", "text": "x"}, {"speaker": "agent", "text": "y"}]', "speaker"),
    ('[{"speaker": "agent"}, {"speaker": "agent", "text": "y"}]', "needs a text"),
    ('{"nope": 1}', "list"),
    ("Agent: " + "x" * 1001 + "\nCustomer: ok", "longer than"),
    ("\n".join(f"Agent: line {i}" for i in range(301)), "at most 300"),
    ("Agent: x\n" * 20_000, "too long"),
])
def test_bad_transcripts_are_rejected_with_a_clear_message(bad, message):
    with pytest.raises(TranscriptError, match=message):
        parse_transcript(bad)


def test_endpoint_scores_a_transcript_and_supervisors_hear_about_it(client):
    with client.websocket_connect("/ws/monitor?name=Sam") as ws:
        ws.receive_json()
        r = client.post("/api/transcripts", json={"agent_name": "Ana", "text": TEXT})
        assert r.status_code == 201
        call = r.json()
        assert call["status"] == "ended" and call["overall"] == 80.0 and call["agent_name"] == "Ana"
        kinds = []
        while "call_ended" not in kinds:
            kinds.append(ws.receive_json()["type"])
    assert kinds[0] == "call_started" and kinds[-1] == "call_ended" and "score" in kinds

    detail = client.get(f"/api/calls/{call['id']}").json()
    assert len(detail["lines"]) == 3 and detail["score"]["kind"] == "final"


def test_endpoint_errors(client, limiter):
    assert client.post("/api/transcripts", json={"agent_name": "Ana", "text": "no labels here"}).status_code == 422
    assert client.post("/api/transcripts", json={"agent_name": "", "text": TEXT}).status_code == 422
    assert client.post("/api/transcripts", json={"agent_name": "Ana"}).status_code == 422
    limiter.burst, limiter.rate = 1, 1 / 60
    limiter._buckets.clear()
    assert client.post("/api/transcripts", json={"agent_name": "Ana", "text": TEXT}).status_code == 201
    assert client.post("/api/transcripts", json={"agent_name": "Ana", "text": TEXT}).status_code == 429


def test_a_model_failure_still_stores_the_call_without_a_score(client, llm):
    llm.fail = True
    r = client.post("/api/transcripts", json={"agent_name": "Ana", "text": TEXT})
    assert r.status_code == 201 and r.json()["overall"] is None
    assert len(client.get(f"/api/calls/{r.json()['id']}").json()["lines"]) == 3
