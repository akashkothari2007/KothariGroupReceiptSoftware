import csv
import io
from datetime import datetime
from fastapi import APIRouter, UploadFile, File
from sqlalchemy import text
from db import engine

router = APIRouter(prefix="/upload", tags=["uploads"])


def parse_date(date_str: str):
    """Parse '13 Mar 2026' format."""
    if not date_str or not date_str.strip():
        return None
    return datetime.strptime(date_str.strip(), "%d %b %Y").date()


def parse_amount(amount_str: str):
    """Parse amount string to float."""
    if not amount_str or not amount_str.strip():
        return None
    return float(amount_str.strip())


def parse_foreign_amount(val: str):
    """Parse '500.00 USD' → (500.00, 'USD')."""
    if not val or not val.strip():
        return None, None
    parts = val.strip().split()
    if len(parts) == 2:
        return float(parts[0]), parts[1]
    return None, None


def parse_city_province(val: str):
    """Parse 'TORONTO\\nON' → ('TORONTO', 'ON')."""
    if not val or not val.strip():
        return None, None
    lines = [l.strip() for l in val.strip().splitlines()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    return lines[0], None


def normalize_country(val: str):
    """CANADA → CA, UNITED STATES → US, etc."""
    if not val:
        return None
    val = val.strip().upper()
    mapping = {"CANADA": "CA", "UNITED STATES": "US"}
    return mapping.get(val, val)


@router.post("/statement")
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

    # Filter valid rows
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

    # Derive cycle dates from transaction dates
    dates = [r["transaction_date"] for r in valid_rows]
    cycle_start = min(dates) if dates else None
    cycle_end = max(dates) if dates else None

    with engine.begin() as conn:
        # Insert statement with cycle dates
        result = conn.execute(
            text("""
                INSERT INTO statements (filename, cycle_start, cycle_end)
                VALUES (:filename, :cycle_start, :cycle_end)
                RETURNING id
            """),
            {"filename": file.filename, "cycle_start": cycle_start, "cycle_end": cycle_end},
        )
        statement_id = result.fetchone()[0]

        # Batch insert all transactions
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

    return {
        "statement_id": str(statement_id),
        "inserted": len(valid_rows),
        "skipped": skipped,
        "total_rows": len(rows),
    }
