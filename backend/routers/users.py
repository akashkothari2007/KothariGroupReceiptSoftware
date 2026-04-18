from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from db import engine
from middleware.auth import get_current_user, require_role

router = APIRouter(prefix="/users", tags=["users"])


class RoleUpdate(BaseModel):
    role: str


# ── Upsert own profile (called on login) ──

@router.post("/upsert")
def upsert_profile(user: dict = Depends(get_current_user)):
    user_id = user.get("sub")
    meta = user.get("user_metadata", {})
    email = user.get("email") or meta.get("email")
    full_name = meta.get("full_name") or meta.get("name")

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO user_profiles (id, email, full_name)
                VALUES (:id, :email, :full_name)
                ON CONFLICT (id) DO UPDATE SET
                    email = COALESCE(EXCLUDED.email, user_profiles.email),
                    full_name = COALESCE(EXCLUDED.full_name, user_profiles.full_name)
            """),
            {"id": user_id, "email": email, "full_name": full_name},
        )
    return {"ok": True}


# ── Get own profile ──

@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    user_id = user.get("sub")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, full_name, role, created_at FROM user_profiles WHERE id = :id"),
            {"id": user_id},
        ).fetchone()

    if not row:
        return {
            "id": user_id,
            "email": user.get("email"),
            "full_name": user.get("user_metadata", {}).get("full_name"),
            "role": "accountant",
            "created_at": None,
        }

    return {
        "id": str(row[0]),
        "email": row[1],
        "full_name": row[2],
        "role": row[3],
        "created_at": row[4].isoformat() if row[4] else None,
    }


# ── List all users (admin only) ──

@router.get("/")
def list_users(user: dict = Depends(require_role("admin"))):
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, email, full_name, role, created_at FROM user_profiles ORDER BY created_at")
        ).fetchall()

    return [
        {
            "id": str(r[0]),
            "email": r[1],
            "full_name": r[2],
            "role": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


# ── Update user role (admin only) ──

@router.patch("/{user_id}/role")
def update_role(user_id: str, body: RoleUpdate, user: dict = Depends(require_role("admin"))):
    if body.role not in ("admin", "manager", "delegate", "accountant"):
        raise HTTPException(status_code=400, detail="Role must be 'admin', 'manager', 'delegate', or 'accountant'")

    if user.get("sub") == user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE user_profiles SET role = :role WHERE id = :id"),
            {"role": body.role, "id": user_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"updated": True}
