from fastapi import APIRouter, Depends
from sqlalchemy import text
from db import engine
from middleware.auth import get_current_user

router = APIRouter(prefix="/lookups", tags=["lookups"], dependencies=[Depends(get_current_user)])


@router.get("/gl-codes")
def list_gl_codes():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, code, name FROM gl_codes ORDER BY code")
        ).fetchall()
    return [{"id": str(r[0]), "code": r[1], "name": r[2]} for r in rows]


@router.get("/companies")
def list_companies():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name FROM companies ORDER BY name")
        ).fetchall()
    return [{"id": str(r[0]), "name": r[1]} for r in rows]
