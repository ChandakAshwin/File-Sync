from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from infra.db.engine import get_session

router = APIRouter()


class TriggerResponse(BaseModel):
    attempt_id: int
    status: str


@router.post("/{cc_pair_id}/backfill", response_model=TriggerResponse)
async def trigger_backfill(cc_pair_id: int, db: Session = Depends(get_session)) -> TriggerResponse:
    # Mimic the existing /api/v1/sync/<id>/trigger endpoint but scoped here
    # Create an index_attempt and dispatch celery task
    res = db.execute(
        text(
            "INSERT INTO index_attempt (connector_credential_pair_id, status, time_started, time_updated) VALUES (:cc, 'IN_PROGRESS', NOW(), NOW()) RETURNING id"
        ),
        {"cc": cc_pair_id},
    )
    attempt_id = res.scalar() or 0
    db.execute(
        text("UPDATE connector_credential_pair SET last_attempt_status = 'IN_PROGRESS' WHERE id = :cc"),
        {"cc": cc_pair_id},
    )
    db.commit()

    # Dispatch via existing Celery worker
    try:
        from workers.celery_worker_functional import connector_doc_fetching_task
    except Exception:
        raise HTTPException(status_code=500, detail="Celery worker not available")

    connector_id = db.execute(
        text("SELECT connector_id FROM connector_credential_pair WHERE id = :cc"),
        {"cc": cc_pair_id},
    ).scalar()
    if connector_id is None:
        raise HTTPException(status_code=404, detail="CC pair not found")

    payload = {
        "connector_credential_pair_id": cc_pair_id,
        "connector_id": connector_id,
        "attempt_id": attempt_id,
        "from_beginning": False,
    }
    connector_doc_fetching_task.delay(payload)

    return TriggerResponse(attempt_id=attempt_id, status="dispatched")
