from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Dict
from urllib.parse import urlencode

import httpx
import json
import time
from typing import Optional

AUTHORIZE_URL = "https://account.box.com/api/oauth2/authorize"
TOKEN_URL = "https://api.box.com/oauth2/token"


def build_authorize_url(*, client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens_async(
    *, client_id: str, client_secret: str, code: str, redirect_uri: str
) -> Dict:
    async with httpx.AsyncClient(timeout=30) as client:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        resp = await client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        payload = resp.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.get("expires_in", 3600))
        return {
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),
            "expires_at": expires_at,
            "scope": payload.get("scope"),
            "token_type": payload.get("token_type"),
        }


async def refresh_tokens_async(*, client_id: str, client_secret: str, refresh_token: str) -> Dict:
    async with httpx.AsyncClient(timeout=30) as client:
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        resp = await client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        payload = resp.json()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=payload.get("expires_in", 3600))
        return {
            "access_token": payload.get("access_token"),
            "refresh_token": payload.get("refresh_token"),
            "expires_at": expires_at,
            "scope": payload.get("scope"),
            "token_type": payload.get("token_type"),
        }


# Backwards-compatible token manager used by older local storage utilities.
# This lightweight implementation reads/writes a local JSON file and refreshes tokens
# using the OAuth endpoints above. In production, tokens should be stored in the DB.
class BoxTokenManager:
    def __init__(self, credentials_file: str = "box_credentials.json", client_id: str | None = None, client_secret: str | None = None):
        self.credentials_file = credentials_file
        # Prefer settings/env; no hardcoded fallbacks
        from config.settings import settings as _settings
        import os as _os
        self.client_id = client_id or (_settings.BOX_CLIENT_ID or _os.getenv("BOX_CLIENT_ID"))
        self.client_secret = client_secret or (_settings.BOX_CLIENT_SECRET or _os.getenv("BOX_CLIENT_SECRET"))
        self.credentials: dict | None = None
        self.load_credentials()

    def load_credentials(self) -> None:
        try:
            import json
            with open(self.credentials_file, "r") as f:
                self.credentials = json.load(f)
        except FileNotFoundError:
            self.credentials = None

    def save_credentials(self) -> None:
        if self.credentials:
            import json
            with open(self.credentials_file, "w") as f:
                json.dump(self.credentials, f, indent=2)

    def _is_token_expired(self) -> bool:
        if not self.credentials or "expires_at" not in self.credentials:
            return True
        try:
            expires_at = self.credentials["expires_at"]
            if isinstance(expires_at, str):
                # Support ISO8601 strings
                from datetime import datetime
                if expires_at.endswith("Z"):
                    expires_at = expires_at.replace("Z", "+00:00")
                expires_at = datetime.fromisoformat(expires_at)
            # Treat timezone-naive as UTC
            if getattr(expires_at, "tzinfo", None) is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            # Refresh 5 minutes early
            return datetime.now(timezone.utc) >= (expires_at - timedelta(minutes=5))
        except Exception:
            return True

    def refresh_access_token(self) -> bool:
        if not self.credentials or not self.credentials.get("box_refresh_token"):
            return False
        import anyio
        try:
            tok = anyio.run(
                refresh_tokens_async,
                client_id=self.client_id,
                client_secret=self.client_secret,
                refresh_token=self.credentials["box_refresh_token"],
            )
            self.credentials["box_access_token"] = tok["access_token"]
            if tok.get("refresh_token"):
                self.credentials["box_refresh_token"] = tok["refresh_token"]
            self.credentials["expires_at"] = tok["expires_at"].isoformat()
            self.save_credentials()
            return True
        except Exception:
            return False

    def get_valid_access_token(self) -> str | None:
        if not self.credentials:
            return None
        if self._is_token_expired():
            if not self.refresh_access_token():
                return None
        return self.credentials.get("box_access_token")

    def test_connection(self) -> bool:
        token = self.get_valid_access_token()
        if not token:
            return False
        try:
            headers = {"Authorization": f"Bearer {token}"}
            with httpx.Client(timeout=15) as client:
                resp = client.get("https://api.box.com/2.0/users/me", headers=headers)
                return resp.status_code == 200
        except Exception:
            return False


# JWT App Authentication for Box
def create_jwt_assertion(*, client_id: str, client_secret: str, private_key: str, private_key_passphrase: Optional[str] = None, user_id: Optional[str] = None) -> str:
    """Create a JWT assertion for Box app authentication.
    
    Args:
        client_id: Box app client ID
        client_secret: Box app client secret  
        private_key: RSA private key (PEM format)
        private_key_passphrase: Optional passphrase for encrypted private key
        user_id: Optional user ID to act as (for user tokens)
    
    Returns:
        JWT token string
    """
    try:
        import jwt
        from cryptography.hazmat.primitives import serialization
        import uuid
    except ImportError:
        raise ImportError("Please install: pip install PyJWT cryptography")
    
    # Load private key
    if isinstance(private_key, str):
        private_key_bytes = private_key.encode('utf-8')
    else:
        private_key_bytes = private_key
        
    key = serialization.load_pem_private_key(
        private_key_bytes,
        password=private_key_passphrase.encode() if private_key_passphrase else None
    )
    
    # Create JWT claims
    now = int(time.time())
    claims = {
        'iss': client_id,
        'sub': user_id or client_id,  # Use client_id for app token, user_id for user token
        'box_sub_type': 'user' if user_id else 'enterprise',
        'aud': 'https://api.box.com/oauth2/token',
        'jti': str(uuid.uuid4()),
        'exp': now + 60,  # Expires in 60 seconds
        'iat': now
    }
    
    # Create and return JWT
    return jwt.encode(claims, key, algorithm='RS256')


def get_app_access_token(*, client_id: str, client_secret: str, private_key: str, private_key_passphrase: Optional[str] = None) -> dict:
    """Get an app access token using JWT authentication.
    
    Returns:
        dict with access_token, token_type, expires_in
    """
    jwt_token = create_jwt_assertion(
        client_id=client_id,
        client_secret=client_secret, 
        private_key=private_key,
        private_key_passphrase=private_key_passphrase
    )
    
    with httpx.Client(timeout=30) as client:
        data = {
            'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion': jwt_token,
            'client_id': client_id,
            'client_secret': client_secret
        }
        
        resp = client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        return resp.json()


class BoxJWTAuth:
    """Box JWT App Authentication Manager.
    
    This provides persistent app-level authentication without token expiration issues.
    """
    
    def __init__(self, client_id: str, client_secret: str, private_key: str, private_key_passphrase: Optional[str] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.private_key = private_key
        self.private_key_passphrase = private_key_passphrase
        self._cached_token = None
        self._token_expires_at = 0
    
    def get_access_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        current_time = time.time()
        
        # Return cached token if still valid (with 5 minute buffer)
        if self._cached_token and current_time < (self._token_expires_at - 300):
            return self._cached_token
        
        # Get new token
        token_data = get_app_access_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            private_key=self.private_key,
            private_key_passphrase=self.private_key_passphrase
        )
        
        self._cached_token = token_data['access_token']
        self._token_expires_at = current_time + token_data.get('expires_in', 3600)
        
        return self._cached_token
    
    def test_connection(self) -> bool:
        """Test the connection with current authentication."""
        try:
            token = self.get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            with httpx.Client(timeout=15) as client:
                # Test with /users/me for app authentication
                resp = client.get('https://api.box.com/2.0/users/me', headers=headers)
                return resp.status_code == 200
        except Exception:
            return False
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get("https://api.box.com/2.0/users/me", headers=headers)
                return resp.status_code == 200
        except Exception:
            return False
