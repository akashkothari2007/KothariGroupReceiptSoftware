from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from db import engine

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionUpdate(BaseModel):
    merchant: Optional[str] = None
    description: Optional[str] = None
    amount_cad: Optional[float] = None
    city: Optional[str] = None
    province: Optional[str] = None
    country: Optional[str] = None
    tax_amount: Optional[float] = None
    company_id: Optional[str] = None
    gl_code_id: Optional[str] = None
    notes: Optional[str] = None
    match_status: Optional[str] = None


ALLOWED_FIELDS = {
    "merchant", "description", "amount_cad", "city", "province",
    "country", "tax_amount", "company_id", "gl_code_id", "notes",
    "match_status",
}


@router.patch("/{transaction_id}")
def update_transaction(transaction_id: str, updates: TransactionUpdate):
    fields = {k: v for k, v in updates.model_dump().items() if v is not None}
    fields = {k: v for k, v in fields.items() if k in ALLOWED_FIELDS}
    if not fields:
        return {"updated": False}

    params = {"tid": transaction_id}
    set_parts = []
    for k, v in fields.items():
        if v == "" or v == 0:
            set_parts.append(f"{k} = NULL")
        else:
            set_parts.append(f"{k} = :{k}")
            params[k] = v

    query = f"UPDATE transactions SET {', '.join(set_parts)} WHERE id = :tid"

    with engine.begin() as conn:
        conn.execute(text(query), params)

    return {"updated": True}
