#!/usr/bin/env python3
"""
Functional Celery Worker copied into WokeloFileSync
- Implements the core indexing pipeline using existing Box connector
- Uses LocalStorage adapter under infra/storage/local.py
"""

import os
import sys
import time
import json
import logging
import socket
from typing import Any, Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
from celery import Celery
from celery.schedules import crontab
from kombu import Queue
from dotenv import load_dotenv

# Ensure project root is in path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Imports adjusted to new layout
from infra.storage.local import LocalStorage
from connectors.registry import get_connector

# Load .env from project root and override any existing env in the process
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=True)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'filesync')

DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create Celery app
app = Celery(
    'wokelo_indexing',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Define queues
PRIMARY_QUEUE = "onyx.primary"
DOCFETCHING_QUEUE = "onyx.docfetching"
DOCPROCESSING_QUEUE = "onyx.docprocessing"
LIGHT_QUEUE = "onyx.light"

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=100,
    task_routes={
        'tasks.check_for_indexing': {'queue': PRIMARY_QUEUE},
        'tasks.connector_doc_fetching_task': {'queue': DOCFETCHING_QUEUE},
        'tasks.docprocessing_task': {'queue': DOCPROCESSING_QUEUE},
        'tasks.check_for_prune': {'queue': LIGHT_QUEUE},
    },
    task_queues=(
        Queue(PRIMARY_QUEUE),
        Queue(DOCFETCHING_QUEUE),
        Queue(DOCPROCESSING_QUEUE),
        Queue(LIGHT_QUEUE),
    ),
    # Enhanced Redis connection settings for Windows-WSL stability
    broker_transport_options={
        'socket_keepalive': True,
        'socket_timeout': 120.0,
        'socket_connect_timeout': 30.0,
        'retry_on_timeout': True,
        'health_check_interval': 30,
        'max_connections': 20,
    },
    result_backend_transport_options={
        'socket_keepalive': True,
        'socket_timeout': 120.0,
        'socket_connect_timeout': 30.0,
        'retry_on_timeout': True,
        'health_check_interval': 30,
        'max_connections': 20,
    },
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_heartbeat=30,
    broker_pool_limit=None,  # Disable connection pooling
    result_backend_max_retries=10,
    result_expires=3600,
    task_reject_on_worker_lost=True,
)

# Schedule periodic tasks
CHECK_MINUTES = int(os.getenv("INDEX_CHECK_INTERVAL_MINUTES", "2"))
PRUNE_MINUTES = int(os.getenv("PRUNE_CHECK_INTERVAL_MINUTES", "5"))
app.conf.beat_schedule = {
    "check-for-indexing": {
        "task": "tasks.check_for_indexing",
        "schedule": crontab(minute=f"*/{CHECK_MINUTES}"),
        "options": {"queue": PRIMARY_QUEUE},
    },
    "check-for-prune": {
        "task": "tasks.check_for_prune",
        "schedule": crontab(minute=f"*/{PRUNE_MINUTES}"),
        "options": {"queue": LIGHT_QUEUE},
    },
}


def get_db_connection():
    engine = create_engine(DATABASE_URL)
    return engine


@app.task(name="tasks.check_for_indexing", bind=True)
def check_for_indexing(self):
    logger.info("🔍 [PRIMARY] Checking for connectors needing indexing...")
    try:
        engine = get_db_connection()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    cc.id as cc_pair_id,
                    c.id as connector_id,
                    c.name,
                    c.source,
                    cc.last_successful_index_time,
                    cc.last_attempt_status
                FROM connector c
                JOIN connector_credential_pair cc ON c.id = cc.connector_id
                WHERE c.source = 'box' 
                AND cc.status = 'ACTIVE'
                AND (
                    cc.last_successful_index_time IS NULL 
                    OR cc.last_successful_index_time < NOW() - INTERVAL '5 minutes'
                    OR cc.last_attempt_status IN ('FAILED', 'NOT_STARTED')
                )
                ORDER BY COALESCE(cc.last_successful_index_time, '1970-01-01'::timestamp) ASC
                LIMIT 5
            """))
            cc_pairs_to_sync = result.fetchall()
            logger.info(f"🎯 Found {len(cc_pairs_to_sync)} connector-credential pairs needing sync")
            for cc_pair in cc_pairs_to_sync:
                cc_pair_id = cc_pair[0]
                connector_id = cc_pair[1]
                connector_name = cc_pair[2]
                logger.info(f"📤 Scheduling sync for connector '{connector_name}' (CC pair {cc_pair_id})")
                attempt_result = conn.execute(text("""
                    INSERT INTO index_attempt (
                        connector_credential_pair_id,
                        status,
                        time_started,
                        time_updated
                    ) VALUES (
                        :cc_pair_id,
                        'IN_PROGRESS',
                        NOW(),
                        NOW()
                    ) RETURNING id
                """), {
                    "cc_pair_id": cc_pair_id,
                    "from_beginning": cc_pair[4] is None
                })
                attempt_id = attempt_result.scalar()
                conn.execute(text("""
                    UPDATE connector_credential_pair 
                    SET last_attempt_status = 'IN_PROGRESS'
                    WHERE id = :cc_pair_id
                """), {"cc_pair_id": cc_pair_id})
                conn.commit()
                payload = {
                    "connector_credential_pair_id": cc_pair_id,
                    "connector_id": connector_id,
                    "attempt_id": attempt_id,
                    "from_beginning": cc_pair[4] is None
                }
                connector_doc_fetching_task.delay(payload)
                logger.info(f"✅ Dispatched fetching task for connector {connector_name}")
            return {"connectors_scheduled": len(cc_pairs_to_sync)}
    except Exception as e:
        logger.error(f"❌ Error in check_for_indexing: {e}")
        import traceback
        traceback.print_exc()
        raise


@app.task(name="tasks.connector_doc_fetching_task", bind=True)
def connector_doc_fetching_task(self, payload: Dict[str, Any]):
    cc_pair_id = payload["connector_credential_pair_id"]
    connector_id = payload["connector_id"]
    attempt_id = payload["attempt_id"]
    from_beginning = payload.get("from_beginning", True)

    logger.info(f"📥 [DOCFETCHING] Starting document fetching for CC pair {cc_pair_id}")

    def _parse_expires_at(val: Any) -> datetime | None:
        try:
            if val is None:
                return None
            if isinstance(val, str):
                if val.endswith("Z"):
                    val = val.replace("Z", "+00:00")
                return datetime.fromisoformat(val)
            return val
        except Exception:
            return None

    def _get_valid_access_token(engine, credential_id: int, connector, creds: dict) -> str:
        import os
        access = creds.get("access_token") or creds.get("box_access_token")
        refresh = creds.get("refresh_token") or creds.get("box_refresh_token")
        exp = _parse_expires_at(creds.get("expires_at"))
        if exp is not None:
            if getattr(exp, "tzinfo", None) is None:
                exp = exp.replace(tzinfo=timezone.utc)
        need_refresh = exp is None or datetime.now(timezone.utc) >= (exp - timedelta(minutes=5))
        if need_refresh and refresh:
            client_id = creds.get("client_id") or os.getenv("BOX_CLIENT_ID")
            client_secret = creds.get("client_secret") or os.getenv("BOX_CLIENT_SECRET")
            try:
                toks = connector.refresh_tokens(client_id=client_id, client_secret=client_secret, refresh_token=refresh)
                access = toks.get("access_token") or access
                new_refresh = toks.get("refresh_token") or refresh
                new_exp = toks.get("expires_at")
                if hasattr(new_exp, "isoformat"):
                    new_exp = new_exp.isoformat()
                creds.update({
                    "access_token": access,
                    "refresh_token": new_refresh,
                    "expires_at": new_exp,
                    "client_id": client_id,
                    "client_secret": client_secret,
                })
                with engine.begin() as conn:
                    conn.execute(text(
                        "UPDATE credential SET credential_json = CAST(:c AS JSON), time_updated = NOW() WHERE id = :id"
                    ), {"c": json.dumps(creds), "id": credential_id})
            except Exception as e:
                logger.error(f"Failed to refresh token: {e}")
        if not access:
            raise RuntimeError("No access token available for Box")
        return access

    try:
        engine = get_db_connection()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    c.name, c.source, c.connector_specific_config,
                    cr.credential_json,
                    cc.id as cc_pair_id,
                    cc.credential_id as credential_id
                FROM connector c
                JOIN connector_credential_pair cc ON c.id = cc.connector_id
                JOIN credential cr ON cc.credential_id = cr.id
                WHERE cc.id = :cc_pair_id AND c.source = 'box'
            """), {"cc_pair_id": cc_pair_id})
            row = result.fetchone()
            if not row:
                raise Exception(f"Connector-credential pair {cc_pair_id} not found")
            connector_name = row[0]
            raw_config = row[2]
            credential_json = row[3]
            credential_id = row[5]
            if isinstance(credential_json, (bytes, memoryview)):
                if isinstance(credential_json, memoryview):
                    credential_json = credential_json.tobytes()
                credential_json = credential_json.decode('utf-8')
            creds = json.loads(credential_json) if isinstance(credential_json, str) else credential_json
            config = raw_config if isinstance(raw_config, dict) else (json.loads(raw_config) if isinstance(raw_config, str) and raw_config else {})
            logger.info(f"📋 Processing connector: {connector_name}")

        # Use new Box connector via registry
        box_connector = get_connector("box")
        access_token = _get_valid_access_token(engine, credential_id, box_connector, creds)

        # Listing
        documents_processed = 0
        logger.info("📚 Starting document listing via Box connector...")
        items = list(box_connector.list_all_items(access_token=access_token, config=config or {}))
        logger.info(f"📋 Retrieved {len(items)} files from Box")

        for item in items:
            documents_processed += 1
            doc_id = f"box:{item.id}"
            logger.info(f"📄 Processing item: {item.name} (ID: {doc_id})")
            with engine.begin() as conn:
                exists = conn.execute(text("SELECT 1 FROM document WHERE id = :id"), {"id": doc_id}).fetchone()
                if exists:
                    logger.info(f"⚠️  Document {doc_id} already exists, skipping")
                else:
                    conn.execute(text("""
                        INSERT INTO document (
                            id, semantic_id, link, doc_updated_at, chunk_count,
                            last_modified, from_ingestion_api, boost, hidden, is_public
                        ) VALUES (
                            :id, :semantic_id, :link, :doc_updated_at, :chunk_count,
                            :last_modified, :from_ingestion_api, :boost, :hidden, :is_public
                        )
                    """), {
                        "id": doc_id,
                        "semantic_id": item.name or doc_id,
                        "link": None,
                        "doc_updated_at": item.modified_at,
                        "chunk_count": 1,
                        "last_modified": datetime.utcnow(),
                        "from_ingestion_api": False,
                        "boost": 0,
                        "hidden": False,
                        "is_public": True
                    })
                conn.execute(text("""
                    INSERT INTO document_by_connector_credential_pair (
                        id, connector_credential_pair_id
                    ) VALUES (
                        :doc_id, :cc_pair_id
                    ) ON CONFLICT (id, connector_credential_pair_id) DO NOTHING
                """), {"doc_id": doc_id, "cc_pair_id": cc_pair_id})

            # Queue processing
            docprocessing_task.delay(f"doc_{attempt_id}_{documents_processed}", [doc_id])

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE index_attempt 
                SET status = 'SUCCESS',
                    time_updated = NOW(),
                    new_docs_indexed = :docs_processed
                WHERE id = :attempt_id
            """), {
                "docs_processed": documents_processed,
                "attempt_id": attempt_id
            })
            conn.execute(text("""
                UPDATE connector_credential_pair
                SET last_successful_index_time = NOW(),
                    last_attempt_status = 'SUCCESS',
                    total_docs_indexed = COALESCE(total_docs_indexed, 0) + :docs_processed
                WHERE id = :cc_pair_id
            """), {
                "docs_processed": documents_processed,
                "cc_pair_id": cc_pair_id
            })

        logger.info(f"🎉 Successfully processed {documents_processed} documents for {connector_name}")

        if documents_processed > 0:
            try:
                logger.info("🔄 Triggering automatic local file sync...")
                file_syncer = LocalStorage(access_token=access_token)
                sync_stats = file_syncer.sync_all_documents()
                logger.info(
                    f"📁 Local sync completed: {sync_stats['downloaded']} new, {sync_stats['updated']} updated, {sync_stats['skipped']} skipped, {sync_stats['errors']} errors"
                )
            except Exception as sync_error:
                logger.error(f"⚠️  Local file sync failed (indexing still successful): {sync_error}")

        try:
            prune_result = _prune_deleted_documents(cc_pair_id)
            logger.info(
                f"🧹 Prune completed: removed_from_db={prune_result['removed_from_db']}, "
                f"removed_local_files={prune_result['removed_local_files']}"
            )
        except Exception as prune_err:
            logger.error(f"⚠️  Prune step failed: {prune_err}")

        return {
            "status": "success",
            "documents_processed": documents_processed,
            "checkpoint_has_more": False
        }

    except Exception as e:
        logger.error(f"❌ Error in connector_doc_fetching_task: {e}")
        import traceback
        traceback.print_exc()
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    UPDATE index_attempt
                    SET status = 'FAILED',
                        time_updated = NOW(),
                        error_msg = :error_msg
                    WHERE id = :attempt_id
                """), {
                    "error_msg": str(e),
                    "attempt_id": attempt_id
                })
                conn.execute(text("""
                    UPDATE connector_credential_pair
                    SET last_attempt_status = 'FAILED'
                    WHERE id = :cc_pair_id
                """), {"cc_pair_id": cc_pair_id})
        except Exception:
            pass
        raise


@app.task(name="tasks.docprocessing_task", bind=True)
def docprocessing_task(self, batch_id: str, document_ids: list[str]):
    logger.info(f"🔄 [DOCPROCESSING] Processing batch {batch_id} with {len(document_ids)} documents")
    try:
        # Download documents if needed, extract text, and index into Elasticsearch
        from infra.storage.local import LocalStorage
        from infra.file_processing.extract_text import extract_text
        from infra.document_index.elasticsearch.index import index_document

        engine = get_db_connection()
        # Determine cc_pair and credentials for these documents (assume same cc_pair within batch)
        cc_pair_id = None
        credential_id = None
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT dc.connector_credential_pair_id, cc.credential_id
                FROM document_by_connector_credential_pair dc
                JOIN connector_credential_pair cc ON cc.id = dc.connector_credential_pair_id
                WHERE dc.id = :doc_id
                LIMIT 1
            """), {"doc_id": document_ids[0]}).fetchone()
            if row:
                cc_pair_id = row[0]
                credential_id = row[1]
        access_token = None
        if credential_id is not None:
            with engine.connect() as conn:
                cred_row = conn.execute(text("SELECT credential_json FROM credential WHERE id = :id"), {"id": credential_id}).fetchone()
            if cred_row:
                cred_json = cred_row[0]
                if isinstance(cred_json, (bytes, memoryview)):
                    if isinstance(cred_json, memoryview):
                        cred_json = cred_json.tobytes()
                    cred_json = cred_json.decode('utf-8')
                creds = json.loads(cred_json) if isinstance(cred_json, str) else cred_json
                # Reuse token helper
                box_connector = get_connector("box")
                def _parse_expires_at(val: Any) -> datetime | None:
                    try:
                        if val is None:
                            return None
                        if isinstance(val, str):
                            if val.endswith("Z"):
                                val = val.replace("Z", "+00:00")
                            return datetime.fromisoformat(val)
                        return val
                    except Exception:
                        return None
                def _get_valid_access_token_local(creds: dict) -> str:
                    import os
                    access = creds.get("access_token") or creds.get("box_access_token")
                    refresh = creds.get("refresh_token") or creds.get("box_refresh_token")
                    exp = _parse_expires_at(creds.get("expires_at"))
                    if exp is not None and getattr(exp, "tzinfo", None) is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    need_refresh = exp is None or datetime.now(timezone.utc) >= (exp - timedelta(minutes=5))
                    if need_refresh and refresh:
                        client_id = creds.get("client_id") or os.getenv("BOX_CLIENT_ID")
                        client_secret = creds.get("client_secret") or os.getenv("BOX_CLIENT_SECRET")
                        try:
                            toks = box_connector.refresh_tokens(client_id=client_id, client_secret=client_secret, refresh_token=refresh)
                            access = toks.get("access_token") or access
                            new_refresh = toks.get("refresh_token") or refresh
                            new_exp = toks.get("expires_at")
                            if hasattr(new_exp, "isoformat"):
                                new_exp = new_exp.isoformat()
                            creds.update({
                                "access_token": access,
                                "refresh_token": new_refresh,
                                "expires_at": new_exp,
                                "client_id": client_id,
                                "client_secret": client_secret,
                            })
                            with engine.begin() as conn:
                                conn.execute(text(
                                    "UPDATE credential SET credential_json = CAST(:c AS JSON), time_updated = NOW() WHERE id = :id"
                                ), {"c": json.dumps(creds), "id": credential_id})
                        except Exception as e:
                            logger.error(f"Failed to refresh token in processing: {e}")
                    if not access:
                        raise RuntimeError("No access token available for Box during processing")
                    return access
                access_token = _get_valid_access_token_local(creds)

        storage = LocalStorage(access_token=access_token)
        processed = 0
        for doc_id in document_ids:
            logger.info(f"📝 Processing document {doc_id}")
            # Initialize variables with defaults
            document_text = ""
            title = doc_id
            link = None
            
            if doc_id.startswith("box:"):
                box_file_id = doc_id.split(":", 1)[1]
                local_info = storage.get_local_file_info(box_file_id)
                local_path = local_info.get('local_path') if local_info else None
                if not local_path:
                    local_path = storage.download_box_file(box_file_id)
                document_text = extract_text(local_path) if local_path else ""
                title = doc_id
                link = f"https://app.box.com/file/{box_file_id}"
                index_document(doc_id=doc_id, title=title, text=document_text, link=link, metadata={"source": "box"})
                processed += 1
            else:
                logger.warning(f"Unknown doc_id scheme: {doc_id}")
                # Still index unknown schemes with basic info
                index_document(doc_id=doc_id, title=title, text=document_text, link=link, metadata={"source": "unknown"})
                processed += 1
        logger.info(f"✅ Batch {batch_id} processing completed; indexed={processed}")
        return {
            "status": "success",
            "batch_id": batch_id,
            "documents_processed": processed
        }
    except Exception as e:
        logger.error(f"❌ Error in docprocessing_task: {e}")
        raise


@app.task(name="tasks.check_for_prune", bind=True)
def check_for_prune(self):
    logger.info("🧹 [LIGHT] Checking for cleanup & prune tasks...")
    removed_total = 0
    removed_local_total = 0
    deleted_attempts = 0
    try:
        engine = get_db_connection()
        with engine.begin() as conn:
            result = conn.execute(text("""
                DELETE FROM index_attempt
                WHERE status = 'FAILED' 
                AND time_updated < NOW() - INTERVAL '1 day'
            """))
            deleted_attempts = result.rowcount or 0
        with engine.connect() as conn:
            cc_rows = conn.execute(text("""
                SELECT cc.id AS cc_pair_id
                FROM connector c
                JOIN connector_credential_pair cc ON c.id = cc.connector_id
                WHERE c.source = 'box' AND cc.status = 'ACTIVE'
            """)).fetchall()
        for (cc_pair_id,) in cc_rows:
            try:
                result = _prune_deleted_documents(cc_pair_id)
                removed_total += result.get('removed_from_db', 0)
                removed_local_total += result.get('removed_local_files', 0)
            except Exception as per_cc_err:
                logger.error(f"Prune failed for CC pair {cc_pair_id}: {per_cc_err}")
                continue
        logger.info(
            f"🧽 Cleanup summary → failed_attempts_deleted={deleted_attempts}, "
            f"db_docs_removed={removed_total}, local_files_removed={removed_local_total}"
        )
        return {
            "cleaned_attempts": deleted_attempts,
            "db_docs_removed": removed_total,
            "local_files_removed": removed_local_total,
        }
    except Exception as e:
        logger.error(f"❌ Error in check_for_prune: {e}")
        raise


@app.task(name="tasks.healthcheck")
def healthcheck():
    return {
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat(),
        "queues": [PRIMARY_QUEUE, DOCFETCHING_QUEUE, DOCPROCESSING_QUEUE, LIGHT_QUEUE]
    }


def _prune_deleted_documents(cc_pair_id: int) -> dict[str, int]:
    logger.info(f"🔍 Starting prune for CC pair {cc_pair_id}...")
    engine = get_db_connection()
    with engine.connect() as conn:
        info = conn.execute(text("""
            SELECT cr.credential_json, cc.credential_id
            FROM connector_credential_pair cc
            JOIN credential cr ON cc.credential_id = cr.id
            WHERE cc.id = :cc_pair_id
        """), {"cc_pair_id": cc_pair_id}).fetchone()
        if not info:
            raise RuntimeError(f"No credentials found for CC pair {cc_pair_id}")
        credential_json = info[0]
        credential_id = info[1]
        if isinstance(credential_json, (bytes, memoryview)):
            if isinstance(credential_json, memoryview):
                credential_json = credential_json.tobytes()
            credential_json = credential_json.decode('utf-8')
        creds = json.loads(credential_json) if isinstance(credential_json, str) else credential_json

    # Build a valid access token (refresh if needed)
    def _parse_expires_at(val: Any) -> datetime | None:
        try:
            if val is None:
                return None
            if isinstance(val, str):
                if val.endswith("Z"):
                    val = val.replace("Z", "+00:00")
                return datetime.fromisoformat(val)
            return val
        except Exception:
            return None

    box_connector = get_connector("box")
    import os
    access = creds.get("access_token") or creds.get("box_access_token")
    refresh = creds.get("refresh_token") or creds.get("box_refresh_token")
    exp = _parse_expires_at(creds.get("expires_at"))
    if exp is not None and getattr(exp, "tzinfo", None) is None:
        exp = exp.replace(tzinfo=timezone.utc)
    need_refresh = exp is None or datetime.now(timezone.utc) >= (exp - timedelta(minutes=5))
    if need_refresh and refresh:
        client_id = creds.get("client_id") or os.getenv("BOX_CLIENT_ID")
        client_secret = creds.get("client_secret") or os.getenv("BOX_CLIENT_SECRET")
        try:
            toks = box_connector.refresh_tokens(client_id=client_id, client_secret=client_secret, refresh_token=refresh)
            access = toks.get("access_token") or access
            new_refresh = toks.get("refresh_token") or refresh
            new_exp = toks.get("expires_at")
            if hasattr(new_exp, "isoformat"):
                new_exp = new_exp.isoformat()
            creds.update({
                "access_token": access,
                "refresh_token": new_refresh,
                "expires_at": new_exp,
                "client_id": client_id,
                "client_secret": client_secret,
            })
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE credential SET credential_json = CAST(:c AS JSON), time_updated = NOW() WHERE id = :id"
                ), {"c": json.dumps(creds), "id": credential_id})
        except Exception as e:
            logger.error(f"Failed to refresh token during prune: {e}")
    if not access:
        raise RuntimeError("No access token available for Box during prune")

    # List items and build current set of ids
    items = list(box_connector.list_all_items(access_token=access, config={"folder_ids": ["0"]}))
    box_file_ids = {i.id for i in items}
    prefixed_box_ids = {f"box:{fid}" for fid in box_file_ids}

    removed_from_db = 0
    removed_local_files = 0

    with engine.begin() as conn:
        db_ids_rows = conn.execute(text("""
            SELECT d.id
            FROM document d
            JOIN document_by_connector_credential_pair dc ON dc.id = d.id
            WHERE dc.connector_credential_pair_id = :cc_pair_id AND d.id LIKE 'box:%'
        """), {"cc_pair_id": cc_pair_id}).fetchall()
        db_ids = {row[0] for row in db_ids_rows}
        to_remove = db_ids - prefixed_box_ids
        if to_remove:
            logger.info(f"🗑️  Will remove {len(to_remove)} documents deleted in Box")
        for doc_id in to_remove:
            conn.execute(text("""
                DELETE FROM document_by_connector_credential_pair
                WHERE id = :doc_id AND connector_credential_pair_id = :cc_pair_id
            """), {"doc_id": doc_id, "cc_pair_id": cc_pair_id})
            other_count = conn.execute(text("""
                SELECT COUNT(*) FROM document_by_connector_credential_pair
                WHERE id = :doc_id
            """), {"doc_id": doc_id}).scalar() or 0
            if other_count == 0:
                conn.execute(text("DELETE FROM document WHERE id = :doc_id"), {"doc_id": doc_id})
                removed_from_db += 1

    # Clean up local files
    try:
        storage = LocalStorage(access_token=access)
        removed_local_files = storage.cleanup_orphaned_files()
    except Exception as e:
        logger.error(f"Failed to clean up local orphaned files: {e}")

    # Clean up Elasticsearch entries
    removed_from_es = 0
    try:
        from infra.document_index.elasticsearch.index import delete_document
        for doc_id in to_remove:
            try:
                delete_document(doc_id)
                removed_from_es += 1
                logger.info(f"🗑️ Removed {doc_id} from Elasticsearch")
            except Exception as e:
                logger.warning(f"Could not remove {doc_id} from Elasticsearch: {e}")
    except Exception as e:
        logger.error(f"Failed to clean up Elasticsearch entries: {e}")

    return {
        "removed_from_db": removed_from_db, 
        "removed_local_files": removed_local_files,
        "removed_from_es": removed_from_es
    }


if __name__ == "__main__":
    try:
        engine = get_db_connection()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("✅ Database connection successful")
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
    app.start()
