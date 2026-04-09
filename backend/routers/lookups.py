from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from db import engine
from middleware.auth import get_current_user

router = APIRouter(prefix="/lookups", tags=["lookups"], dependencies=[Depends(get_current_user)])


# ── GL Codes ──

@router.get("/gl-codes")
def list_gl_codes():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, code, name FROM gl_codes ORDER BY code")
        ).fetchall()
    return [{"id": str(r[0]), "code": r[1], "name": r[2]} for r in rows]


class GlCodeCreate(BaseModel):
    code: str
    name: str


class GlCodeUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None


@router.post("/gl-codes")
def create_gl_code(body: GlCodeCreate):
    with engine.begin() as conn:
        row = conn.execute(
            text("INSERT INTO gl_codes (code, name) VALUES (:code, :name) RETURNING id, code, name"),
            {"code": body.code.strip(), "name": body.name.strip()},
        ).fetchone()
    return {"id": str(row[0]), "code": row[1], "name": row[2]}


@router.patch("/gl-codes/{gl_code_id}")
def update_gl_code(gl_code_id: str, body: GlCodeUpdate):
    fields = {k: v.strip() for k, v in body.model_dump().items() if v is not None}
    if not fields:
        return {"updated": False}

    params = {"gid": gl_code_id}
    set_parts = []
    for k, v in fields.items():
        set_parts.append(f"{k} = :{k}")
        params[k] = v

    with engine.begin() as conn:
        result = conn.execute(
            text(f"UPDATE gl_codes SET {', '.join(set_parts)} WHERE id = :gid"),
            params,
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="GL code not found")
    return {"updated": True}


@router.delete("/gl-codes/{gl_code_id}")
def delete_gl_code(gl_code_id: str):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE transactions SET gl_code_id = NULL WHERE gl_code_id = :gid"),
            {"gid": gl_code_id},
        )
        result = conn.execute(
            text("DELETE FROM gl_codes WHERE id = :gid"),
            {"gid": gl_code_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="GL code not found")
    return {"deleted": True}


# ── Companies ──

@router.get("/companies")
def list_companies():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name FROM companies ORDER BY name")
        ).fetchall()
    return [{"id": str(r[0]), "name": r[1]} for r in rows]


class CompanyCreate(BaseModel):
    name: str


class CompanyUpdate(BaseModel):
    name: Optional[str] = None


@router.post("/companies")
def create_company(body: CompanyCreate):
    with engine.begin() as conn:
        row = conn.execute(
            text("INSERT INTO companies (name) VALUES (:name) RETURNING id, name"),
            {"name": body.name.strip()},
        ).fetchone()
    return {"id": str(row[0]), "name": row[1]}


@router.patch("/companies/{company_id}")
def update_company(company_id: str, body: CompanyUpdate):
    if not body.name:
        return {"updated": False}

    with engine.begin() as conn:
        result = conn.execute(
            text("UPDATE companies SET name = :name WHERE id = :cid"),
            {"name": body.name.strip(), "cid": company_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"updated": True}


@router.delete("/companies/{company_id}")
def delete_company(company_id: str):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE transactions SET company_id = NULL WHERE company_id = :cid"),
            {"cid": company_id},
        )
        result = conn.execute(
            text("DELETE FROM companies WHERE id = :cid"),
            {"cid": company_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Company not found")
    return {"deleted": True}
