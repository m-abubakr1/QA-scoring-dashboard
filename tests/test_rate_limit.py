from app.rate_limit import ConnectionCounter, RateLimiter


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_burst_then_blocked_then_refills():
    clock = Clock()
    lim = RateLimiter(per_minute=60, burst=3, clock=clock)  # one token per second
    assert [lim.check("a").allowed for _ in range(3)] == [True, True, True]
    blocked = lim.check("a")
    assert not blocked.allowed and 0 < blocked.retry_after <= 1
    clock.now += 1.0
    assert lim.check("a").allowed
    assert not lim.check("a").allowed


def test_clients_have_separate_buckets():
    lim = RateLimiter(per_minute=60, burst=1, clock=Clock())
    assert lim.check("a").allowed
    assert not lim.check("a").allowed
    assert lim.check("b").allowed


def test_bucket_never_holds_more_than_burst():
    clock = Clock()
    lim = RateLimiter(per_minute=60, burst=2, clock=clock)
    clock.now += 1000
    assert [lim.check("a").allowed for _ in range(3)] == [True, True, False]


def test_connection_counter():
    c = ConnectionCounter(limit=2)
    assert c.acquire("ip") and c.acquire("ip")
    assert not c.acquire("ip")
    c.release("ip")
    assert c.acquire("ip")


def test_http_returns_429_with_retry_after(client, limiter):
    limiter.burst, limiter.rate = 2, 1 / 60
    limiter._buckets.clear()
    body = {"agent_name": "Sam"}
    first = client.post("/api/calls", json=body)
    assert first.status_code == 201 and first.headers["X-RateLimit-Remaining"] == "1"
    assert client.post("/api/calls", json=body).status_code == 201
    blocked = client.post("/api/calls", json=body)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert "Try again in" in blocked.json()["detail"]


def test_cheap_endpoints_are_not_limited(client, limiter):
    limiter.burst, limiter.rate = 1, 1 / 60
    limiter._buckets.clear()
    for _ in range(5):
        assert client.get("/health").status_code == 200
        assert client.get("/api/rubric").status_code == 200
