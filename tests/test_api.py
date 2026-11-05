import time

from app.config import settings
from tests.fakes import good_score


def wait_for(condition, seconds=3.0):
    """Scoring runs in the background, so poll instead of checking once."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def new_call(client, agent="Sam"):
    return client.post("/api/calls", json={"agent_name": agent}).json()


def say(client, call_id, speaker, text):
    return client.post(f"/api/calls/{call_id}/lines", json={"speaker": speaker, "text": text})


def test_full_call_flow(client, llm):
    call = new_call(client)
    assert call["status"] == "live" and call["agent_name"] == "Sam"
    assert say(client, call["id"], "agent", "Thanks for calling, this is Sam.").status_code == 201
    assert say(client, call["id"], "customer", "My internet is down.").json()["seq"] == 2
    ended = client.post(f"/api/calls/{call['id']}/end").json()
    assert ended["status"] == "ended" and ended["overall"] == 80.0

    detail = client.get(f"/api/calls/{call['id']}").json()
    assert [ln["speaker"] for ln in detail["lines"]] == ["agent", "customer"]
    assert detail["score"]["kind"] == "final" and detail["score"]["rubric_version"] == "support-v1"
    assert len(detail["score"]["criteria"]) == 6


def test_live_score_runs_every_n_lines(client, llm):
    call = new_call(client)  # the client fixture sets score_every_lines to 2
    say(client, call["id"], "agent", "Hello, this is Sam.")
    say(client, call["id"], "customer", "Hi.")
    assert wait_for(lambda: client.get(f"/api/calls/{call['id']}").json()["score"] is not None)
    assert client.get(f"/api/calls/{call['id']}").json()["score"]["kind"] == "live"


def test_validation_and_missing_or_ended_calls(client):
    assert client.post("/api/calls", json={"agent_name": ""}).status_code == 422
    call = new_call(client)
    assert say(client, call["id"], "robot", "beep").status_code == 422
    assert say(client, call["id"], "agent", "").status_code == 422
    assert say(client, 999, "agent", "hi").status_code == 404
    assert client.post("/api/calls/999/end").status_code == 404
    say(client, call["id"], "agent", "a")
    client.post(f"/api/calls/{call['id']}/end")
    assert say(client, call["id"], "agent", "too late").status_code == 409
    assert client.post(f"/api/calls/{call['id']}/end").status_code == 409
    assert client.get("/api/calls/999").status_code == 404


def test_model_failure_while_ending_still_closes_the_call_without_a_score(client, llm):
    call = new_call(client)
    say(client, call["id"], "agent", "hi")
    say(client, call["id"], "customer", "hello")
    llm.fail = True
    # supervisors are told the scoring failed, but the call itself is still closed
    r = client.post(f"/api/calls/{call['id']}/end")
    assert r.status_code == 200 and r.json()["status"] == "ended" and r.json()["overall"] is None


def test_list_filter_and_agent_summary(client, llm):
    for agent, score in [("Sam", 5), ("Sam", 1), ("Ana", 3)]:
        every = ["greeting", "empathy", "resolution", "compliance", "professionalism", "closing"]
        llm.responder = lambda s, u, sc=score: good_score(scores={k: sc for k in every})
        call = new_call(client, agent)
        say(client, call["id"], "agent", "hi")
        say(client, call["id"], "customer", "hello")
        client.post(f"/api/calls/{call['id']}/end")

    assert len(client.get("/api/calls").json()) == 3
    assert [c["agent_name"] for c in client.get("/api/calls?agent=Ana").json()] == ["Ana"]
    low = client.get("/api/calls?max_score=60").json()
    assert sorted(c["overall"] for c in low) == [20.0, 60.0]
    assert client.get("/api/calls?status=live").json() == []
    assert client.get("/api/calls?max_score=500").status_code == 422

    agents = {a["agent_name"]: a for a in client.get("/api/agents").json()}
    assert agents["Sam"]["calls"] == 2 and agents["Sam"]["average"] == 60.0 and agents["Ana"]["average"] == 60.0


def test_rubric_and_samples(client):
    rubric = client.get("/api/rubric").json()
    assert rubric["version"] == "support-v1" and round(sum(c["weight"] for c in rubric["criteria"]), 2) == 1.0
    assert any(c["critical"] for c in rubric["criteria"])
    assert isinstance(client.get("/api/samples").json(), list)
    assert client.post("/api/simulate", json={"sample_id": "nope"}).status_code == 404
    assert client.post("/api/simulate", json={"sample_id": "x", "speed": 0}).status_code == 422


def test_api_key_is_enforced_when_set(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    assert client.get("/api/rubric").status_code == 401
    assert client.get("/api/rubric", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/rubric", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/health").status_code == 200
