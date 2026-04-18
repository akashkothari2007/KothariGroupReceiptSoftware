import os
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt, jwk
from sqlalchemy import text
from db import engine

SUPABASE_URL = os.getenv("SUPABASE_URL")
JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"

security = HTTPBearer()

# Cache the public key so we don't fetch JWKS on every request
_cached_key = None


def _get_signing_key():
    global _cached_key
    if _cached_key is not None:
        return _cached_key
    resp = httpx.get(JWKS_URL)
    resp.raise_for_status()
    keys = resp.json()["keys"]
    _cached_key = jwk.construct(keys[0])
    return _cached_key


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    try:
        key = _get_signing_key()
        payload = jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            audience="authenticated",
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    return payload


ROLE_HIERARCHY = ["accountant", "delegate", "manager", "admin"]


def require_role(minimum_role: str):
    """Returns a FastAPI dependency that checks the user has at least the given role."""
    min_rank = ROLE_HIERARCHY.index(minimum_role)

    def _checker(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> dict:
        user = get_current_user(credentials)
        user_id = user.get("sub")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT role FROM user_profiles WHERE id = :id"),
                {"id": user_id},
            ).fetchone()
        role = row[0] if row else "accountant"
        rank = ROLE_HIERARCHY.index(role) if role in ROLE_HIERARCHY else 0
        if rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{minimum_role} access required",
            )
        user["role"] = role
        return user

    return _checker


# Backwards compat alias
require_admin = require_role("admin")
