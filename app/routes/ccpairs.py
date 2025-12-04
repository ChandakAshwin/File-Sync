from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from infra.db.engine import get_session
from infra.db import models

router = APIRouter()


class CreateCCPairRequest(BaseModel):
    connector_name: str  # e.g., 'box'
    connector_source: str = "box"
    credential_id: int
    name: str | None = None
    connector_config: dict | None = None


class CreateCCPairResponse(BaseModel):
    cc_pair_id: int


@router.post("/create", response_model=CreateCCPairResponse)
async def create_ccpair(req: CreateCCPairRequest, db: Session = Depends(get_session)) -> CreateCCPairResponse:
    # Get or create connector
    connector = db.query(models.Connector).filter(models.Connector.name == req.connector_name).one_or_none()
    if connector is None:
        connector = models.Connector(name=req.connector_name, source=req.connector_source, connector_specific_config=req.connector_config)
        db.add(connector)
        db.flush()

    # Ensure credential exists
    credential = db.get(models.Credential, req.credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="Credential not found")

    # Create CC pair
    cc = models.ConnectorCredentialPair(
        name=req.name,
        connector_id=connector.id,
        credential_id=credential.id,
        status="ACTIVE",
    )
    db.add(cc)
    db.flush()

    return CreateCCPairResponse(cc_pair_id=cc.id)
