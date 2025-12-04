from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

from app.routes import oauth, ccpairs as ccpairs_routes, sync as sync_routes

# Load .env early so os.getenv sees values, using absolute project path and overriding
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
load_dotenv(dotenv_path=os.path.join(_PROJECT_ROOT, ".env"), override=True)

app = FastAPI(title="Wokelo File Sync API")

# DB connection (legacy inline engine for existing endpoints)
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'password')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'filesync')
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(DATABASE_URL)


class ConnectorIn(BaseModel):
    name: str
    source: str
    input_type: str | None = None


class CredentialIn(BaseModel):
    credential_json: dict


class CCPairIn(BaseModel):
    connector_id: int
    credential_id: int
    name: str | None = None


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}

# New modular routes
app.include_router(oauth.router, prefix="/auth", tags=["oauth"])
app.include_router(ccpairs_routes.router, prefix="/ccpairs", tags=["ccpairs"])
app.include_router(sync_routes.router, prefix="/sync", tags=["sync"])


@app.get("/api/v1/connectors")
def list_connectors():
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name, source FROM connector ORDER BY id"))
        return [dict(id=r[0], name=r[1], source=r[2]) for r in rows]


@app.post("/api/v1/connectors")
def create_connector(conn_in: ConnectorIn):
    with engine.begin() as conn:
        res = conn.execute(text(
            "INSERT INTO connector (name, source, input_type, time_created, time_updated) VALUES (:n, :s, :i, NOW(), NOW()) RETURNING id"
        ), {"n": conn_in.name, "s": conn_in.source, "i": conn_in.input_type})
        return {"id": res.scalar()}


@app.post("/api/v1/credentials")
def create_credential(cred_in: CredentialIn):
    with engine.begin() as conn:
        import json
        res = conn.execute(text(
            "INSERT INTO credential (credential_json, time_created, time_updated) VALUES (:c::json, NOW(), NOW()) RETURNING id"
        ), {"c": json.dumps(cred_in.credential_json)})
        return {"id": res.scalar()}


@app.post("/api/v1/cc_pairs")
def create_ccpair(cc_in: CCPairIn):
    with engine.begin() as conn:
        res = conn.execute(text(
            """
            INSERT INTO connector_credential_pair (name, connector_id, credential_id, status, time_created, time_updated)
            VALUES (:n, :cid, :crid, 'ACTIVE', NOW(), NOW()) RETURNING id
            """
        ), {"n": cc_in.name, "cid": cc_in.connector_id, "crid": cc_in.credential_id})
        return {"id": res.scalar()}


@app.post("/api/v1/sync/{cc_pair_id}/trigger")
def trigger_sync(cc_pair_id: int):
    # Create attempt and dispatch the fetching task
    from workers.celery_worker_functional import connector_doc_fetching_task
    with engine.begin() as conn:
        res = conn.execute(text(
            "INSERT INTO index_attempt (connector_credential_pair_id, status, time_started, time_updated) VALUES (:cc, 'IN_PROGRESS', NOW(), NOW()) RETURNING id"
        ), {"cc": cc_pair_id})
        attempt_id = res.scalar()
        # Find connector id
        r2 = conn.execute(text(
            "SELECT connector_id FROM connector_credential_pair WHERE id = :cc"
        ), {"cc": cc_pair_id}).fetchone()
        if not r2:
            raise HTTPException(status_code=404, detail="CC pair not found")
        connector_id = r2[0]
    payload = {
        "connector_credential_pair_id": cc_pair_id,
        "connector_id": connector_id,
        "attempt_id": attempt_id,
        "from_beginning": False,
    }
    connector_doc_fetching_task.delay(payload)
    return {"status": "dispatched", "attempt_id": attempt_id}


@app.get("/api/v1/search")
def search_endpoint(q: str, size: int = 10):
    from infra.document_index.elasticsearch.index import search
    res = search(q=q, size=size)
    return res
