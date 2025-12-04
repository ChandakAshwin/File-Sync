from __future__ import annotations

import json
from sqlalchemy import create_engine, text

import workers.celery_worker_functional as worker


def _create_sqlite_schema(engine):
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS credential (
              id INTEGER PRIMARY KEY,
              credential_json TEXT
            );
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS connector_credential_pair (
              id INTEGER PRIMARY KEY,
              connector_id INTEGER,
              credential_id INTEGER
            );
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS document (
              id TEXT PRIMARY KEY,
              semantic_id TEXT,
              link TEXT,
              doc_updated_at TEXT,
              chunk_count INTEGER,
              last_modified TEXT,
              from_ingestion_api INTEGER,
              boost INTEGER,
              hidden INTEGER,
              is_public INTEGER
            );
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS document_by_connector_credential_pair (
              id TEXT,
              connector_credential_pair_id INTEGER
            );
            """
        ))


def test_prune_deleted_documents(monkeypatch, tmp_path):
    # In-memory SQLite engine
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    _create_sqlite_schema(engine)

    # Monkeypatch DB connection factory
    monkeypatch.setattr(worker, "get_db_connection", lambda: engine)

    # Monkeypatch connector registry to return a dummy box connector with list_all_items
    class DummyItem:
        def __init__(self, id):
            self.id = id
    class DummyBox:
        name = "box"
        def list_all_items(self, *, access_token: str, config: dict):
            yield DummyItem("keep1")
    monkeypatch.setattr(worker, "get_connector", lambda name: DummyBox())

    # Monkeypatch LocalStorage cleanup to avoid filesystem
    class DummyStorage:
        def cleanup_orphaned_files(self):
            return 0
    monkeypatch.setattr(worker, "LocalStorage", DummyStorage)

    # Seed DB rows
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO credential (id, credential_json) VALUES (1, :c)"
        ), {"c": json.dumps({"access_token": "AT", "refresh_token": "RT"})})
        conn.execute(text(
            "INSERT INTO connector_credential_pair (id, connector_id, credential_id) VALUES (1, 10, 1)"
        ))
        conn.execute(text(
            "INSERT INTO document (id, semantic_id, link, doc_updated_at, chunk_count, last_modified, from_ingestion_api, boost, hidden, is_public)"
            " VALUES ('box:keep1', 'box:keep1', NULL, NULL, 1, NULL, 0, 0, 0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO document (id, semantic_id, link, doc_updated_at, chunk_count, last_modified, from_ingestion_api, boost, hidden, is_public)"
            " VALUES ('box:gone1', 'box:gone1', NULL, NULL, 1, NULL, 0, 0, 0, 1)"
        ))
        conn.execute(text(
            "INSERT INTO document_by_connector_credential_pair (id, connector_credential_pair_id) VALUES ('box:keep1', 1)"
        ))
        conn.execute(text(
            "INSERT INTO document_by_connector_credential_pair (id, connector_credential_pair_id) VALUES ('box:gone1', 1)"
        ))

    # Run prune
    result = worker._prune_deleted_documents(1)
    assert result["removed_from_db"] == 1

    # Verify DB state
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM document ORDER BY id")).fetchall()
        ids = [r[0] for r in rows]
        assert ids == ["box:keep1"]