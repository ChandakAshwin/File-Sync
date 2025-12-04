from __future__ import annotations

import types

from app.routes import oauth as oauth_routes


class DummyRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    def get(self, key: str) -> str | None:
        return self.store.get(key)


def test_oauth_start_sets_state_and_returns_url(monkeypatch):
    # monkeypatch redis
    dummy = DummyRedis()
    monkeypatch.setattr(oauth_routes, "get_redis", lambda: dummy)

    # call handler
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    res = client.get("/auth/box/start")
    assert res.status_code == 200
    data = res.json()
    assert "redirect_url" in data
    assert data["redirect_url"].startswith("https://account.box.com/")
