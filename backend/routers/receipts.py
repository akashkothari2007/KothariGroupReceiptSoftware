import os
import logging
import threading
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy import text
from supabase import create_client
from db import engine
from middleware.auth import get_current_user, require_role
from services.receipt_ingest import ingest_receipt_bytes, _run_extraction_bg, _run_email_body_extraction_bg
from services.match_run import run_matching_for_receipt
from services.match_writer import remove_match

logger = logging.getLogger("receipts")
router = APIRouter(prefix="/receipts", tags=["receipts"], dependencies=[Depends(get_current_user)])

BUCKET = "receipts"

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# ── Shared helper ──

def _format_receipt_row(r):
    """Map a SQL row from the standard receipt query to a dict."""
    return {
        "id": str(r[0]),
        "image_url": r[1],
        "file_name": r[2],
        "file_type": r[3],
        "source": r[4],
        "merchant_name": r[5],
        "receipt_date": str(r[6]) if r[6] else None,
        "tax_amount": float(r[7]) if r[7] is not None else None,
        "tax_type": r[8],
        "total_amount": float(r[9]) if r[9] is not None else None,
        "match_status": r[10],
        "processing_status": r[11],
        "created_at": str(r[12]),
        "transaction_id": str(r[13]) if r[13] else None,
        "tx_merchant": r[14],
        "tx_amount": float(r[15]) if r[15] is not None else None,
        "tx_date": str(r[16]) if r[16] else None,
        "country": r[17],
        "city": r[18],
        "province": r[19],
        "subtotal": float(r[20]) if r[20] is not None else None,
        "statement_id": str(r[21]) if r[21] else None,
        "card_account_id": str(r[22]) if r[22] else None,
        "card_account_name": r[23],
        "cycle_start": str(r[24]) if r[24] else None,
        "cycle_end": str(r[25]) if r[25] else None,
    }

_BASE_SELECT = """
    SELECT r.id, r.image_url, r.file_name, r.file_type, r.source,
           r.merchant_name, r.receipt_date, r.tax_amount, r.tax_type,
           r.total_amount, r.match_status, r.processing_status, r.created_at,
           r.transaction_id, t.merchant as tx_merchant, t.amount_cad as tx_amount,
           t.transaction_date as tx_date, r.country, r.city, r.province,
           r.subtotal,
           s.id as statement_id, ca.id as card_account_id,
           ca.name as card_account_name, s.cycle_start, s.cycle_end
    FROM receipts r
    LEFT JOIN transactions t ON t.id = r.transaction_id
    LEFT JOIN statements s ON s.id = t.statement_id
    LEFT JOIN card_accounts ca ON ca.id = s.card_account_id
"""

MATCH_STATUS_MAP = {
    "unmatched": "unmatched",
    "unsure": "matched_unsure",
    "matched": "matched_sure",
}


# manual upload of receipts
@router.post("/upload")
async def upload_receipt(file: UploadFile = File(...), user: dict = Depends(require_role("delegate"))):
    logger.info(f"Upload request: filename={file.filename}, content_type={file.content_type}, size={file.size}")
    contents = await file.read()
    try:
        result = ingest_receipt_bytes(contents, file.filename, file.content_type, source="manual")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Upload failed for {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    return result


@router.get("")
def list_receipts(
    view: str = Query("byMonth"),
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    limit: int = Query(20),
    offset: int = Query(0),
    match_status: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    statement_id: Optional[str] = Query(None),
):
    where_clauses = []
    params = {}

    # Match status filter
    if match_status:
        statuses = [MATCH_STATUS_MAP[s.strip()] for s in match_status.split(",") if s.strip() in MATCH_STATUS_MAP]
        if statuses:
            placeholders = ", ".join(f":ms_{i}" for i in range(len(statuses)))
            where_clauses.append(f"r.match_status IN ({placeholders})")
            for i, s in enumerate(statuses):
                params[f"ms_{i}"] = s

    # Statement expand: fetch receipts for a specific statement
    if statement_id:
        where_clauses.append("t.statement_id = :statement_id")
        params["statement_id"] = statement_id
        where_part = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"{_BASE_SELECT}{where_part} ORDER BY r.receipt_date DESC NULLS LAST, r.created_at DESC"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return {"receipts": [_format_receipt_row(r) for r in rows], "has_more": False}

    # Search view
    if q and q.strip():
        where_clauses.append("r.merchant_name ILIKE :q")
        params["q"] = f"%{q.strip()}%"
        where_part = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        fetch_limit = limit + 1
        params["lim"] = fetch_limit
        params["off"] = offset
        sql = f"{_BASE_SELECT}{where_part} ORDER BY r.created_at DESC LIMIT :lim OFFSET :off"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        return {"receipts": [_format_receipt_row(r) for r in rows], "has_more": has_more}

    # By Month view
    if view == "byMonth":
        import datetime
        if year and month:
            month_start = datetime.date(year, month, 1)
            if month == 12:
                month_end = datetime.date(year + 1, 1, 1)
            else:
                month_end = datetime.date(year, month + 1, 1)
            # Include receipts in date range OR receipts with no date (if not filtered out by match_status)
            date_clause = "(r.receipt_date >= :month_start AND r.receipt_date < :month_end)"
            # Also include no-date receipts unless match_status filter is set
            if not match_status:
                date_clause = f"({date_clause} OR r.receipt_date IS NULL)"
            where_clauses.append(date_clause)
            params["month_start"] = month_start
            params["month_end"] = month_end
        where_part = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sql = f"{_BASE_SELECT}{where_part} ORDER BY r.receipt_date DESC NULLS LAST, r.created_at DESC"
        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return {"receipts": [_format_receipt_row(r) for r in rows], "has_more": False}

    # Recent view (default)
    where_part = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    fetch_limit = limit + 1
    params["lim"] = fetch_limit
    params["off"] = offset
    sql = f"{_BASE_SELECT}{where_part} ORDER BY r.created_at DESC LIMIT :lim OFFSET :off"
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    return {"receipts": [_format_receipt_row(r) for r in rows], "has_more": has_more}


@router.get("/statement-groups")
def list_statement_groups():
    """Lightweight endpoint: returns only statement group headers with receipt counts."""
    sql = """
        SELECT s.id, ca.name, s.cycle_start, s.cycle_end, COUNT(r.id)
        FROM receipts r
        JOIN transactions t ON t.id = r.transaction_id
        JOIN statements s ON s.id = t.statement_id
        JOIN card_accounts ca ON ca.id = s.card_account_id
        WHERE r.match_status IN ('matched_sure', 'matched_unsure')
        GROUP BY s.id, ca.name, s.cycle_start, s.cycle_end
        ORDER BY s.cycle_end DESC NULLS LAST
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [
        {
            "statement_id": str(r[0]),
            "card_account_name": r[1],
            "cycle_start": str(r[2]) if r[2] else None,
            "cycle_end": str(r[3]) if r[3] else None,
            "receipt_count": r[4],
        }
        for r in rows
    ]


@router.get("/processing")
def list_processing_receipts():
    """Returns only receipts with pending/processing status for targeted polling."""
    sql = f"""{_BASE_SELECT} WHERE r.processing_status IN ('pending', 'processing')
              ORDER BY r.created_at DESC"""
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()
    return [_format_receipt_row(r) for r in rows]


# receipt metadata
@router.get("/{receipt_id}")
def get_receipt(receipt_id: str):
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, image_url, file_type, file_name, source,
                       merchant_name, receipt_date, subtotal, tax_amount, tax_type,
                       total_amount, country, raw_ai_response,
                       email_message_id, email_received_at, email_sender,
                       transaction_id, match_status, processing_status, created_at
                FROM receipts
                WHERE id = :id
            """),
            {"id": receipt_id},
        )
        r = result.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Receipt not found")

    return {
        "id": str(r[0]),
        "image_url": r[1],
        "file_type": r[2],
        "file_name": r[3],
        "source": r[4],
        "merchant_name": r[5],
        "receipt_date": str(r[6]) if r[6] else None,
        "subtotal": float(r[7]) if r[7] is not None else None,
        "tax_amount": float(r[8]) if r[8] is not None else None,
        "tax_type": r[9],
        "total_amount": float(r[10]) if r[10] is not None else None,
        "country": r[11],
        "raw_ai_response": r[12],
        "company_id": None,
        "gl_code_id": None,
        "email_message_id": r[13],
        "email_received_at": str(r[14]) if r[14] else None,
        "email_sender": r[15],
        "transaction_id": str(r[16]) if r[16] else None,
        "match_status": r[17],
        "processing_status": r[18],
        "created_at": str(r[19]),
    }


RECEIPT_ALLOWED_FIELDS = {
    "merchant_name", "receipt_date", "subtotal", "tax_amount", "tax_type",
    "total_amount", "country", "city", "province", "notes",
    "match_status", "processing_status", "raw_ai_response",
}


class ReceiptUpdate(BaseModel):
    merchant_name: Optional[str] = None
    receipt_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_type: Optional[str] = None
    total_amount: Optional[float] = None
    country: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    match_status: Optional[str] = None
    processing_status: Optional[str] = None


MATCH_RELEVANT_FIELDS = {"merchant_name", "receipt_date", "total_amount", "country"}

CANADIAN_TAX_TYPES = {"HST", "GST"}


def _sync_receipt_edits_to_transaction(receipt_id: str, transaction_id: str, fields: dict, edited_tx_fields: set):
    """Propagate receipt field edits to the linked transaction (mirrors apply_match logic)."""
    from services.rules import apply_rules

    with engine.begin() as conn:
        set_parts = []
        params = {"tid": transaction_id}
        needs_rules = False

        if "city" in edited_tx_fields:
            val = fields.get("city")
            if val and val != "":
                set_parts.append("city = :r_city")
                params["r_city"] = val
            else:
                set_parts.append("city = NULL")
            set_parts.append("company_id = NULL")
            needs_rules = True

        if "province" in edited_tx_fields:
            val = fields.get("province")
            if val and val != "":
                set_parts.append("province = :r_province")
                params["r_province"] = val
            else:
                set_parts.append("province = NULL")
            needs_rules = True

        if "country" in edited_tx_fields:
            val = fields.get("country")
            if val and val != "":
                set_parts.append("country = :r_country")
                params["r_country"] = val
            else:
                set_parts.append("country = NULL")

        if "tax_amount" in edited_tx_fields or "tax_type" in edited_tx_fields:
            # Re-derive tax using same logic as apply_match
            receipt = conn.execute(
                text("SELECT tax_amount, tax_type FROM receipts WHERE id = :rid"),
                {"rid": receipt_id},
            ).fetchone()
            if receipt:
                r_tax = float(receipt[0]) if receipt[0] is not None else None
                r_type = receipt[1]
                is_canadian = r_type and r_type.upper() in CANADIAN_TAX_TYPES
                if is_canadian and r_tax is not None:
                    set_parts.append("tax_amount = :tx_tax")
                    params["tx_tax"] = r_tax
                else:
                    set_parts.append("tax_amount = 0")

        if set_parts:
            conn.execute(
                text(f"UPDATE transactions SET {', '.join(set_parts)} WHERE id = :tid"),
                params,
            )

    if needs_rules:
        try:
            apply_rules(transaction_id)
        except Exception as e:
            logger.error(f"Rules failed after receipt edit sync for tx={transaction_id}: {e}", exc_info=True)


@router.patch("/{receipt_id}")
def patch_receipt(receipt_id: str, updates: ReceiptUpdate, user: dict = Depends(require_role("delegate"))):
    fields = {k: v for k, v in updates.model_dump().items() if v is not None and k in RECEIPT_ALLOWED_FIELDS}
    if not fields:
        return {"updated": False}

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT transaction_id, processing_status FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Receipt not found")

        is_unmatched = row[0] is None
        is_completed = row[1] == "completed"

        params = {"rid": receipt_id}
        set_parts = []
        for k, v in fields.items():
            if v == "":
                set_parts.append(f"{k} = NULL")
            else:
                set_parts.append(f"{k} = :{k}")
                params[k] = v

        query = f"UPDATE receipts SET {', '.join(set_parts)} WHERE id = :rid"
        conn.execute(text(query), params)

        # Sync match_status to linked transaction (e.g. confirming unsure → sure)
        if "match_status" in fields and not is_unmatched:
            conn.execute(
                text("UPDATE transactions SET match_status = :status WHERE matched_receipt_id = :rid"),
                {"status": fields["match_status"], "rid": receipt_id},
            )

    # If receipt is matched, propagate relevant field changes to the linked transaction
    TX_SYNC_FIELDS = {"city", "province", "country", "tax_amount", "tax_type"}
    edited_tx_fields = set(fields.keys()) & TX_SYNC_FIELDS
    if edited_tx_fields and not is_unmatched:
        transaction_id = str(row[0])
        try:
            _sync_receipt_edits_to_transaction(receipt_id, transaction_id, fields, edited_tx_fields)
        except Exception as e:
            logger.error(f"Failed syncing receipt edits to tx={transaction_id}: {e}", exc_info=True)

    # Auto-rematch if user edited a matching-relevant field and receipt is unmatched
    edited_match_fields = set(fields.keys()) & MATCH_RELEVANT_FIELDS
    if edited_match_fields and is_unmatched and is_completed:
        def _bg():
            try:
                run_matching_for_receipt(receipt_id)
            except Exception as e:
                logger.error(f"Auto-rematch after edit failed for {receipt_id}: {e}", exc_info=True)
        threading.Thread(target=_bg, daemon=True).start()
        return {"updated": True, "rematching": True}

    return {"updated": True}


@router.post("/{receipt_id}/retry")
async def retry_receipt(receipt_id: str, background_tasks: BackgroundTasks, user: dict = Depends(require_role("delegate"))):
    """Re-process a failed receipt extraction."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT image_url, file_type, processing_status, source, transaction_id FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if row[2] not in ("failed", "completed"):
        raise HTTPException(status_code=400, detail=f"Receipt is {row[2]}, not retryable")

    # Clean up existing match on both sides before resetting
    if row[4]:
        remove_match(str(row[4]))

    # Reset extracted fields and status
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE receipts
                SET processing_status = 'pending',
                    merchant_name = NULL, receipt_date = NULL, subtotal = NULL,
                    tax_amount = NULL, tax_type = NULL, total_amount = NULL,
                    country = NULL, city = NULL, province = NULL, raw_ai_response = NULL
                WHERE id = :id
            """),
            {"id": receipt_id},
        )

    logger.info(f"Retrying extraction for receipt {receipt_id}")
    if row[3] == "email" and row[1] == "text/html":
        background_tasks.add_task(_run_email_body_extraction_bg, receipt_id, row[0])
    else:
        background_tasks.add_task(_run_extraction_bg, receipt_id, row[0], row[1])
    return {"retrying": True, "receipt_id": receipt_id}


@router.post("/{receipt_id}/rematch")
def rematch_receipt(receipt_id: str, user: dict = Depends(require_role("delegate"))):
    """Re-run matching for this receipt against all transactions."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT processing_status FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if row[0] != "completed":
        raise HTTPException(status_code=400, detail=f"Receipt is {row[0]}, not matchable")

    def _bg():
        try:
            matches = run_matching_for_receipt(receipt_id)
            logger.info(f"Rematch for {receipt_id}: {len(matches)} match(es)")
        except Exception as e:
            logger.error(f"Rematch failed for {receipt_id}: {e}", exc_info=True)

    threading.Thread(target=_bg, daemon=True).start()
    return {"rematching": True}


@router.delete("/{receipt_id}/match")
def unmatch_receipt(receipt_id: str, user: dict = Depends(require_role("delegate"))):
    """Remove the match on this receipt (unlinks from transaction)."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT transaction_id FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if not row[0]:
        raise HTTPException(status_code=400, detail="Receipt is not matched")

    ok = remove_match(str(row[0]))
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to remove match")
    return {"unmatched": True}


@router.get("/{receipt_id}/url")
def get_receipt_url(receipt_id: str):
    """Return a short-lived signed URL for the receipt file (60 min)."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT image_url FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        )
        row = result.fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Receipt not found")

    signed = supabase.storage.from_(BUCKET).create_signed_url(row[0], 3600)
    return {"url": signed["signedURL"]}


@router.delete("/{receipt_id}")
def delete_receipt(receipt_id: str, user: dict = Depends(require_role("delegate"))):
    # Fetch the receipt to get the storage path
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT image_url FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        )
        row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")

    storage_path = row[0]

    # Delete from Supabase Storage
    if storage_path:
        try:
            supabase.storage.from_(BUCKET).remove([storage_path])
        except Exception:
            pass  # Continue even if storage delete fails

    # Clear reference on transactions and delete receipt row
    with engine.begin() as conn:
        conn.execute(
            text("""UPDATE transactions
                    SET matched_receipt_id = NULL, match_status = 'unmatched', tax_amount = NULL
                    WHERE matched_receipt_id = :id"""),
            {"id": receipt_id},
        )
        conn.execute(
            text("DELETE FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        )

    return {"deleted": True}
