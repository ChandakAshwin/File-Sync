from __future__ import annotations

import types
from connectors.registry import get_connector


def test_box_refresh_tokens(monkeypatch):
    # Mock httpx.AsyncClient.post used in connectors.box.auth.refresh_tokens_async
    class FakeResp:
        def __init__(self):
            self.status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "access_token": "new_access",
                "refresh_token": "new_refresh",
                "expires_in": 3600,
                "token_type": "bearer",
            }
    class FakeAsyncClient:
        def __init__(self, timeout=30):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, data=None):
            return FakeResp()

    import connectors.box.auth as box_auth
    monkeypatch.setattr(box_auth, "httpx", types.SimpleNamespace(AsyncClient=FakeAsyncClient))

    box = get_connector("box")
    result = box.refresh_tokens(client_id="id", client_secret="sec", refresh_token="old_refresh")
    assert result["access_token"] == "new_access"
    assert result["refresh_token"] == "new_refresh"
    assert result["expires_at"] is not None


def test_box_list_all_items(monkeypatch):
    # Mock httpx.Client.get used in connectors.box.connector
    class FakeResp:
        def __init__(self, data):
            self._data = data
        def raise_for_status(self):
            return None
        def json(self):
            return self._data

    class FakeClient:
        def __init__(self, timeout=60):
            pass
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def get(self, url, headers=None, params=None):
            if "/folders/0/items" in url:
                return FakeResp({
                    "entries": [
                        {"type": "folder", "id": "100", "name": "Sub"},
                        {"type": "file", "id": "f1", "name": "File1", "size": 10, "sha1": "abc"},
                    ]
                })
            if "/folders/100/items" in url:
                return FakeResp({
                    "entries": [
                        {"type": "file", "id": "f2", "name": "File2", "size": 20, "sha1": "def"},
                    ]
                })
            return FakeResp({"entries": []})

    import connectors.box.connector as box_conn
    monkeypatch.setattr(box_conn, "httpx", types.SimpleNamespace(Client=FakeClient))

    box = get_connector("box")
    items = list(box.list_all_items(access_token="tok", config={"folder_ids": ["0"]}))
    ids = sorted(i.id for i in items)
    assert ids == ["f1", "f2"]