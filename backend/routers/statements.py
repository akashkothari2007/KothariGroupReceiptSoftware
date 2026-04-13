import csv
import io
import logging
import threading
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy import text
from db import engine
from middleware.auth import get_current_user
from services.match_run import run_matching_for_statement

logger = logging.getLogger("statements")

router = APIRouter(prefix="/statements", tags=["statements"], dependencies=[Depends(get_current_user)])

matching_status: dict[str, str] = {}


def parse_date(date_str: str):
    if not date_str or not date_str.strip():
        return None
    return datetime.strptime(date_str.strip(), "%d %b %Y").date()


def parse_amount(amount_str: str):
    if not amount_str or not amount_str.strip():
        return None
    return float(amount_str.strip())


def parse_foreign_amount(val: str):
    """Parse '500.00 USD' or '228.000,00 TRY' or '2,295.00 USD' -> (float, currency)."""
    if not val or not val.strip():
        return None, None
    parts = val.strip().split()
    if len(parts) == 2:
        num_str = parts[0]
        if ',' in num_str and num_str.rfind(',') > num_str.rfind('.'):
            num_str = num_str.replace('.', '').replace(',', '.')
        else:
            num_str = num_str.replace(',', '')
        try:
            return float(num_str), parts[1]
        except ValueError:
            return None, None
    return None, None


def parse_city_province(val: str):
    if not val or not val.strip():
        return None, None
    lines = [l.strip() for l in val.strip().splitlines()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    return lines[0], None


def normalize_country(val: str):
    if not val:
        return None
    val = val.strip().upper()
    mapping = {"CANADA": "CA", "UNITED STATES": "US"}
    return mapping.get(val, val)


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


@router.post("/upload")
async def upload_statement(file: UploadFile = File(...)):
    contents = await file.read()
    text_content = contents.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))

    rows = []
    for row in reader:
        foreign_amount, foreign_currency = parse_foreign_amount(
            row.get("Foreign Spend Amount", "")
        )
        city, province = parse_city_province(row.get("City / Province", ""))
        reference = row.get("Reference", "").strip().strip("'")

        rows.append({
            "transaction_date": parse_date(row.get("Date", "")),
            "merchant": (row.get("Merchant") or "").strip() or None,
            "description": (row.get("Description") or "").strip() or None,
            "amount_cad": parse_amount(row.get("Amount", "")),
            "foreign_amount": foreign_amount,
            "foreign_currency": foreign_currency,
            "exchange_rate": parse_amount(row.get("Exchange Rate", "")),
            "city": city,
            "province": province,
            "country": normalize_country(row.get("Country", "")),
            "reference": reference or None,
            "card_member": (row.get("Card Member") or "").strip() or None,
        })

    valid_rows = []
    skipped = 0
    for row in rows:
        if row["transaction_date"] is None or row["amount_cad"] is None:
            skipped += 1
            continue
        valid_rows.append({
            "transaction_date": row["transaction_date"],
            "merchant": row["merchant"] or row["description"] or "Unknown",
            "description": row["description"],
            "amount_cad": row["amount_cad"],
            "foreign_amount": row["foreign_amount"],
            "foreign_currency": row["foreign_currency"],
            "exchange_rate": row["exchange_rate"],
            "city": row["city"],
            "province": row["province"],
            "country": row["country"],
            "reference": row["reference"],
        })

    dates = [r["transaction_date"] for r in valid_rows]
    cycle_start = min(dates) if dates else None
    cycle_end = max(dates) if dates else None

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO statements (filename, cycle_start, cycle_end)
                VALUES (:filename, :cycle_start, :cycle_end)
                RETURNING id
            """),
            {"filename": file.filename, "cycle_start": cycle_start, "cycle_end": cycle_end},
        )
        statement_id = result.fetchone()[0]

        if valid_rows:
            params = [{"statement_id": statement_id, **r} for r in valid_rows]
            conn.execute(
                text("""
                    INSERT INTO transactions (
                        statement_id, transaction_date, merchant, description,
                        amount_cad, foreign_amount, foreign_currency, exchange_rate,
                        city, province, country, reference
                    ) VALUES (
                        :statement_id, :transaction_date, :merchant, :description,
                        :amount_cad, :foreign_amount, :foreign_currency, :exchange_rate,
                        :city, :province, :country, :reference
                    )
                """),
                params,
            )

    sid = str(statement_id)
    matching_status[sid] = "matching"

    def _bg_match():
        try:
            matches = run_matching_for_statement(sid)
            logger.info(f"Statement {sid}: auto-matched {len(matches)} transactions")
            matching_status[sid] = "done"
        except Exception as e:
            logger.error(f"Auto-matching failed for statement {sid}: {e}", exc_info=True)
            matching_status[sid] = "error"

    threading.Thread(target=_bg_match, daemon=True).start()

    return {
        "statement_id": sid,
        "inserted": len(valid_rows),
        "skipped": skipped,
        "total_rows": len(rows),
        "matching_status": "matching",
    }


@router.get("/{statement_id}/transactions")
def get_transactions(statement_id: str):
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT t.id, t.transaction_date, t.merchant, t.description,
                       t.amount_cad, t.foreign_amount, t.foreign_currency,
                       t.tax_amount,
                       t.company_id, t.gl_code_id, t.expense_type_id,
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
            "expense_type_id": str(r[10]) if r[10] else None,
            "match_status": r[11],
            "matched_receipt_id": str(r[12]) if r[12] else None,
            "receipt_file_name": r[13],
            "receipt_merchant": r[14],
            "receipt_file_type": r[15],
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
