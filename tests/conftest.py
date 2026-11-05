import os

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, make_session_factory
from app.hub import Monitor
from app.main import app
from app.rate_limit import ConnectionCounter, RateLimiter, get_connections, get_limiter
from tests.fakes import FakeLLM


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def monitor(llm, tmp_path):
    # SQLite by default. To run the same tests on Postgres:
    #   TEST_DATABASE_URL=postgresql+psycopg://qa:qa@localhost:5432/qa_test pytest
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    factory = make_session_factory(url)
    yield Monitor(factory, lambda: llm)
    Base.metadata.drop_all(factory.kw["bind"])  # leave an empty database for the next test


@pytest.fixture
def limiter():
    # roomy by default so ordinary tests never hit the limit
    return RateLimiter(per_minute=6000, burst=1000)


@pytest.fixture
def conns():
    return ConnectionCounter(limit=50)


@pytest.fixture
def client(monitor, limiter, conns, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    monkeypatch.setattr(settings, "score_every_lines", 2)
    app.state.monitor = monitor
    app.dependency_overrides[get_limiter] = lambda: limiter
    app.dependency_overrides[get_connections] = lambda: conns
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    app.state.monitor = None
