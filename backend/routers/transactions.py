import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from db import engine
from middleware.auth import get_current_user
from services.match_writer import apply_match, remove_match
from services.rules import apply_rules

logger = logging.getLogger("transactions")

router = APIRouter(prefix="/transactions", tags=["transactions"], dependencies=[Depends(get_current_user)])


@router.get("/{transaction_id}")
def get_transaction(transaction_id: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT t.id, t.statement_id, t.merchant, t.amount_cad, t.transaction_date,
                       s.card_account_id
                FROM transactions t
                LEFT JOIN statements s ON s.id = t.statement_id
                WHERE t.id = :tid
            """),
            {"tid": transaction_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "id": str(row[0]),
        "statement_id": str(row[1]) if row[1] else None,
        "merchant": row[2],
        "amount_cad": float(row[3]) if row[3] is not None else None,
        "transaction_date": row[4].isoformat() if row[4] else None,
        "card_account_id": str(row[5]) if row[5] else None,
    }


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
    expense_type_id: Optional[str] = None
    notes: Optional[str] = None
    match_status: Optional[str] = None


ALLOWED_FIELDS = {
    "merchant", "description", "amount_cad", "city", "province",
    "country", "tax_amount", "company_id", "gl_code_id", "expense_type_id", "notes",
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

    # Re-run rules when user clears company/gl_code or changes city/merchant
    # (fields that rules depend on were modified)
    rules_fields = {"city", "province", "company_id", "gl_code_id", "merchant", "description"}
    if set(fields.keys()) & rules_fields:
        try:
            apply_rules(transaction_id)
        except Exception as e:
            logger.error(f"Rules failed after PATCH for tx={transaction_id}: {e}", exc_info=True)

    return {"updated": True}


class ManualMatch(BaseModel):
    receipt_id: str


@router.post("/{transaction_id}/match")
def match_transaction(transaction_id: str, body: ManualMatch):
    ok = apply_match(transaction_id, body.receipt_id, "matched_sure", "manual")
    if not ok:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return {"matched": True}


@router.delete("/{transaction_id}/match")
def unmatch_transaction(transaction_id: str):
    ok = remove_match(transaction_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No match to remove")
    return {"unmatched": True}
