from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import settings
from connectors.registry import list_connectors
from connectors.registry import get_connector
from core.redis import get_redis
from infra.db.engine import get_session
from infra.db import models

router = APIRouter()

STATE_KEY_FMT = "oauth_state:{state}"
STATE_TTL_SECONDS = 10 * 60


class AuthorizeResponse(BaseModel):
    redirect_url: str


@router.get("/box/start", response_model=AuthorizeResponse)
async def oauth_start(
    request: Request,
    desired_return_url: Optional[str] = Query(default=None),
) -> AuthorizeResponse:
    """Initiate OAuth flow for Box and return the provider authorization URL."""
    if "box" not in list_connectors():
        raise HTTPException(status_code=400, detail="Box connector not registered")
    state = str(uuid.uuid4())

    # Store minimal state in Redis to validate callback and pass through desired return URL
    r = get_redis()
    r.setex(
        STATE_KEY_FMT.format(state=state),
        STATE_TTL_SECONDS,
        json.dumps({"desired_return_url": desired_return_url or ""}),
    )

    box = get_connector("box")
    if not settings.BOX_CLIENT_ID:
        raise HTTPException(status_code=500, detail="BOX_CLIENT_ID not configured")
    url = box.build_authorize_url(
        client_id=settings.BOX_CLIENT_ID,
        redirect_uri=settings.BOX_REDIRECT_URI,
        state=state,
    )
    return AuthorizeResponse(redirect_url=url)


class CallbackResponse(BaseModel):
    credential_id: int
    redirect_url: Optional[str] = None


@router.get("/box/callback", response_model=CallbackResponse)
async def oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_session),
) -> CallbackResponse:
    # Verify state
    r = get_redis()
    raw = r.get(STATE_KEY_FMT.format(state=state))
    if not raw:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    state_obj = json.loads(raw)

    # Exchange code for tokens
    box = get_connector("box")
    if not settings.BOX_CLIENT_ID or not settings.BOX_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="BOX client credentials not configured")
    try:
        token_info = await box.exchange_code_for_tokens_async(
            client_id=settings.BOX_CLIENT_ID,
            client_secret=settings.BOX_CLIENT_SECRET,
            code=code,
            redirect_uri=settings.BOX_REDIRECT_URI,
        )
    except Exception as e:
        import httpx as _httpx
        if isinstance(e, _httpx.HTTPStatusError):
            # Surface Box error to client
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
        raise

    # Normalize token payload for JSON storage and include client credentials for refresh
    expires_at_val = token_info.get("expires_at")
    if hasattr(expires_at_val, "isoformat"):
        expires_at_val = expires_at_val.isoformat()
    token_json = {
        "access_token": token_info.get("access_token") or token_info.get("box_access_token"),
        "refresh_token": token_info.get("refresh_token") or token_info.get("box_refresh_token"),
        "expires_at": expires_at_val,
        "client_id": settings.BOX_CLIENT_ID,
        "client_secret": settings.BOX_CLIENT_SECRET,
        "scope": token_info.get("scope"),
        "token_type": token_info.get("token_type"),
    }

    # Persist credential (Onyx-style schema)
    cred = models.Credential(credential_json=token_json, admin_public=True)
    db.add(cred)
    db.flush()

    # Optional: also write to local BoxTokenManager credentials file for legacy flows
    try:
        from connectors.box.auth import BoxTokenManager
        manager = BoxTokenManager()
        manager.credentials = {
            "box_access_token": token_info.get("access_token") or token_info.get("box_access_token"),
            "box_refresh_token": token_info.get("refresh_token") or token_info.get("box_refresh_token"),
            "expires_at": token_json.get("expires_at"),
        }
        manager.save_credentials()
    except Exception:
        pass

    return CallbackResponse(
        credential_id=cred.id,
        redirect_url=state_obj.get("desired_return_url") or None,
    )
