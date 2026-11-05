import pytest
from starlette.websockets import WebSocketDisconnect

from app import samples
from app.config import settings
from tests.fakes import good_score

ALL = ["greeting", "empathy", "resolution", "compliance", "professionalism", "closing"]


def all_scores(value, **override):
    return good_score(scores={**{c: value for c in ALL}, **override})


def until(ws, *types, limit=60):
    """Read messages until one of the given types shows up. Returns everything read."""
    seen = []
    for _ in range(limit):
        msg = ws.receive_json()
        seen.append(msg)
        if msg["type"] in types:
            return seen
    raise AssertionError(f"never saw {types}, got {[m['type'] for m in seen]}")


def watch(client, name="Sam"):
    return client.websocket_connect(f"/ws/monitor?name={name}")


def two_line_call(client, agent="Ana"):
    call = client.post("/api/calls", json={"agent_name": agent}).json()
    client.post(f"/api/calls/{call['id']}/lines", json={"speaker": "agent", "text": "Hello, this is Ana."})
    client.post(f"/api/calls/{call['id']}/lines", json={"speaker": "customer", "text": "My bill is wrong."})
    return call


def test_join_gives_state_and_tells_the_others(client):
    client.post("/api/calls", json={"agent_name": "Ana"})
    with watch(client, "Sam") as a:
        joined = a.receive_json()
        assert joined["type"] == "joined" and joined["you"]["name"] == "Sam"
        assert [w["name"] for w in joined["watchers"]] == ["Sam"]
        assert [c["agent_name"] for c in joined["calls"]] == ["Ana"]
        with watch(client, "Lee") as b:
            assert [w["name"] for w in b.receive_json()["watchers"]] == ["Sam", "Lee"]
            note = a.receive_json()
            assert note["type"] == "presence" and note["event"] == "join" and note["watcher"]["name"] == "Lee"
        left = a.receive_json()
        assert left["event"] == "leave" and [w["name"] for w in left["watchers"]] == ["Sam"]


def test_a_call_is_pushed_to_supervisors_as_it_happens(client):
    with watch(client) as ws:
        ws.receive_json()
        call = two_line_call(client)
        client.post(f"/api/calls/{call['id']}/end")
        msgs = until(ws, "call_ended")
    kinds = [m["type"] for m in msgs]
    assert kinds[0] == "call_started" and kinds.count("line") == 2 and kinds[-1] == "call_ended"
    finals = [m for m in msgs if m["type"] == "score" and m["kind"] == "final"]
    assert len(finals) == 1 and finals[0]["score"]["overall"] == 80.0
    assert msgs[-1]["call"]["overall"] == 80.0 and msgs[-1]["call"]["status"] == "ended"
    assert kinds.index("line") < kinds.index("call_ended")


def test_live_score_is_pushed_after_every_n_lines(client):
    with watch(client) as ws:
        ws.receive_json()
        two_line_call(client)
        live = until(ws, "score")[-1]
    assert live["kind"] == "live" and live["score"]["overall"] == 80.0


def test_a_compliance_failure_raises_one_alert(client, llm):
    llm.responder = lambda s, u: all_scores(4, compliance=1)
    with watch(client) as ws:
        ws.receive_json()
        call = two_line_call(client)
        alert = until(ws, "alert")[-1]
        assert alert["alert"]["type"] == "compliance" and alert["alert"]["severity"] == "high"
        assert "1/5" in alert["alert"]["message"] and alert["call_id"] == call["id"]
        client.post(f"/api/calls/{call['id']}/end")
        rest = until(ws, "call_ended")
    assert not any(m["type"] == "alert" and m["alert"]["type"] == "compliance" for m in rest)  # not repeated
    detail = client.get(f"/api/calls/{call['id']}").json()
    assert [a["type"] for a in detail["alerts"]] == ["compliance"]


def test_a_big_drop_in_the_live_score_raises_an_alert(client, llm):
    answers = iter([all_scores(5), all_scores(3)])
    llm.responder = lambda s, u: next(answers)
    with watch(client) as ws:
        ws.receive_json()
        call = two_line_call(client)
        until(ws, "score")  # first live score: 100
        for text in ("one", "two"):
            client.post(f"/api/calls/{call['id']}/lines", json={"speaker": "agent", "text": text})
        alert = until(ws, "alert")[-1]["alert"]
    assert alert["type"] == "score_drop" and "100.0 to 60.0" in alert["message"]


def test_a_low_final_score_raises_an_alert(client, llm):
    llm.responder = lambda s, u: all_scores(2)  # overall 40, under the 50 threshold
    with watch(client) as ws:
        ws.receive_json()
        call = two_line_call(client)
        client.post(f"/api/calls/{call['id']}/end")
        msgs = until(ws, "call_ended")
    assert any(m["type"] == "alert" and m["alert"]["type"] == "low_score" for m in msgs)
    assert client.get(f"/api/calls/{call['id']}").json()["overall"] == 40.0


def test_scoring_failure_is_reported_not_hidden(client, llm):
    llm.fail = True
    with watch(client) as ws:
        ws.receive_json()
        two_line_call(client)
        err = until(ws, "score_error")[-1]
    assert "boom" in err["message"]


def test_notes_reach_everyone_and_are_saved(client):
    call = two_line_call(client)
    with watch(client, "Sam") as a, watch(client, "Lee") as b:
        a.receive_json(); b.receive_json(); a.receive_json()
        a.send_json({"type": "note", "call_id": call["id"], "text": "Check with the team lead"})
        for ws in (a, b):
            note = until(ws, "note")[-1]
            assert note["note"]["author"] == "Sam" and note["note"]["text"] == "Check with the team lead"
    assert client.get(f"/api/calls/{call['id']}").json()["notes"][0]["text"] == "Check with the team lead"


def test_bad_messages_get_an_error_and_the_socket_stays_open(client):
    with watch(client) as ws:
        ws.receive_json()
        ws.send_text("not json")
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "note", "call_id": "x", "text": "hi"})
        assert "needs a call_id" in ws.receive_json()["message"]
        ws.send_json({"type": "note", "call_id": 999, "text": "hi"})
        assert ws.receive_json()["message"] == "No call with that id"
        ws.send_json({"type": "dance"})
        assert "Unknown message type" in ws.receive_json()["message"]
        ws.send_json({"type": "pong"})  # nothing comes back for this


def test_notes_are_rate_limited(client, limiter):
    call = two_line_call(client)
    limiter.burst, limiter.rate = 1, 1 / 60
    limiter._buckets.clear()
    with watch(client) as ws:
        ws.receive_json()
        ws.send_json({"type": "note", "call_id": call["id"], "text": "first"})
        until(ws, "note")
        ws.send_json({"type": "note", "call_id": call["id"], "text": "second"})
        limited = ws.receive_json()
    assert limited["type"] == "rate_limited" and limited["retry_after"] > 0


def test_simulator_replays_a_call_live(client, monkeypatch):
    sample = {"id": "demo", "title": "Demo", "agent_name": "Ana", "lines": [
        {"speaker": "agent", "text": "Hello, this is Ana."}, {"speaker": "customer", "text": "Hi, my bill is wrong."},
        {"speaker": "agent", "text": "Let me look."}, {"speaker": "customer", "text": "Thanks."}]}
    monkeypatch.setattr(samples, "get_sample", lambda sid: sample if sid == "demo" else None)
    with watch(client) as ws:
        ws.receive_json()
        started = client.post("/api/simulate", json={"sample_id": "demo", "speed": 50}).json()
        msgs = until(ws, "call_ended")
    assert started["agent_name"] == "Ana"
    assert [m["type"] for m in msgs if m["type"] in ("call_started", "line", "call_ended")] == \
        ["call_started"] + ["line"] * 4 + ["call_ended"]
    assert client.get(f"/api/calls/{started['id']}").json()["status"] == "ended"


def test_too_many_connections_from_one_address(client, conns):
    conns.limit = 2
    with watch(client), watch(client):
        with pytest.raises(WebSocketDisconnect) as exc:
            with watch(client):
                pass
        assert exc.value.code == 1013
    with watch(client):  # slots are freed when the sockets close
        pass


def test_server_pings_and_hangs_up_on_idle_clients(client, monkeypatch):
    monkeypatch.setattr(settings, "ws_ping_seconds", 0.05)
    monkeypatch.setattr(settings, "ws_idle_timeout_seconds", 0.2)
    with watch(client) as ws:
        ws.receive_json()
        assert ws.receive_json() == {"type": "ping"}
        with pytest.raises(WebSocketDisconnect) as exc:
            for _ in range(20):
                ws.receive_json()
        assert exc.value.code == 1001


def test_api_key_is_checked_on_the_socket(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "secret")
    with pytest.raises(WebSocketDisconnect):
        with watch(client):
            pass
    with client.websocket_connect("/ws/monitor?api_key=secret") as ws:
        assert ws.receive_json()["type"] == "joined"
