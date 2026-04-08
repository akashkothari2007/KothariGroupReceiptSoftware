from fastapi import APIRouter, Depends
from sqlalchemy import text
from db import engine
from middleware.auth import get_current_user
from routers.uploads import matching_status

router = APIRouter(prefix="/statements", tags=["statements"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_statements():
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT s.id, s.filename, s.uploaded_at,
                       COUNT(t.id) as transaction_count,
                       COALESCE(SUM(t.amount_cad), 0) as total_amount
                FROM statements s
                LEFT JOIN transactions t ON t.statement_id = s.id
                GROUP BY s.id
                ORDER BY s.uploaded_at DESC
            """)
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "filename": r[1],
            "uploaded_at": r[2].isoformat() if r[2] else None,
            "transaction_count": r[3],
            "total_amount": float(r[4]),
            "matching_status": matching_status.get(str(r[0])),
        }
        for r in rows
    ]


@router.get("/{statement_id}/transactions")
def get_transactions(statement_id: str):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT t.id, t.transaction_date, t.merchant, t.description,
                       t.amount_cad, t.foreign_amount, t.foreign_currency,
                       t.tax_amount,
                       t.company_id, t.gl_code_id,
                       t.match_status, t.matched_receipt_id,
                       r.file_name as receipt_file_name,
                       r.merchant_name as receipt_merchant,
                       r.file_type as receipt_file_type
                FROM transactions t
                LEFT JOIN receipts r ON r.id = t.matched_receipt_id
                WHERE t.statement_id = :sid
                ORDER BY t.transaction_date DESC, t.merchant
            """),
            {"sid": statement_id},
        ).fetchall()
    return [
        {
            "id": str(r[0]),
            "transaction_date": r[1].isoformat() if r[1] else None,
            "merchant": r[2],
            "description": r[3],
            "amount_cad": float(r[4]) if r[4] is not None else None,
            "foreign_amount": float(r[5]) if r[5] is not None else None,
            "foreign_currency": r[6],
            "tax_amount": float(r[7]) if r[7] is not None else None,
            "company_id": str(r[8]) if r[8] else None,
            "gl_code_id": str(r[9]) if r[9] else None,
            "match_status": r[10],
            "matched_receipt_id": str(r[11]) if r[11] else None,
            "receipt_file_name": r[12],
            "receipt_merchant": r[13],
            "receipt_file_type": r[14],
        }
        for r in rows
    ]


@router.delete("/{statement_id}")
def delete_statement(statement_id: str):
    matching_status.pop(statement_id, None)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM statements WHERE id = :sid"),
            {"sid": statement_id},
        )
    return {"deleted": True}
