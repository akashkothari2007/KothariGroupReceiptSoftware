import os
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt, jwk

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
