import os
import logging
import threading
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import text
from supabase import create_client
from db import engine
from middleware.auth import get_current_user
from services.receipt_ingest import ingest_receipt_bytes
from services.match_run import run_matching_for_receipt
from services.match_writer import remove_match

logger = logging.getLogger("receipts")
router = APIRouter(prefix="/receipts", tags=["receipts"], dependencies=[Depends(get_current_user)])

BUCKET = "receipts"

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


@router.post("/upload")
async def upload_receipt(file: UploadFile = File(...)):
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
def list_receipts():
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT r.id, r.image_url, r.file_name, r.file_type, r.source,
                       r.merchant_name, r.receipt_date, r.tax_amount, r.tax_type,
                       r.total_amount, r.match_status, r.processing_status, r.created_at,
                       r.transaction_id, t.merchant as tx_merchant, t.amount_cad as tx_amount,
                       t.transaction_date as tx_date, r.country
                FROM receipts r
                LEFT JOIN transactions t ON t.id = r.transaction_id
                ORDER BY r.created_at DESC
            """)
        )
        rows = result.fetchall()

    return [
        {
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
        }
        for r in rows
    ]


@router.get("/{receipt_id}")
def get_receipt(receipt_id: str):
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                SELECT id, image_url, file_type, file_name, source,
                       merchant_name, receipt_date, subtotal, tax_amount, tax_type,
                       total_amount, country, raw_ai_response, company_id, gl_code_id,
                       email_message_id, email_received_at, email_sender,
                       transaction_id, match_status, match_method, processing_status, created_at
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
        "company_id": str(r[13]) if r[13] else None,
        "gl_code_id": str(r[14]) if r[14] else None,
        "email_message_id": r[15],
        "email_received_at": str(r[16]) if r[16] else None,
        "email_sender": r[17],
        "transaction_id": str(r[18]) if r[18] else None,
        "match_status": r[19],
        "match_method": r[20],
        "processing_status": r[21],
        "created_at": str(r[22]),
    }


RECEIPT_ALLOWED_FIELDS = {
    "merchant_name", "receipt_date", "subtotal", "tax_amount", "tax_type",
    "total_amount", "country", "company_id", "gl_code_id", "notes",
    "match_status", "match_method", "processing_status", "raw_ai_response",
}


class ReceiptUpdate(BaseModel):
    merchant_name: Optional[str] = None
    receipt_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_type: Optional[str] = None
    total_amount: Optional[float] = None
    country: Optional[str] = None
    company_id: Optional[str] = None
    gl_code_id: Optional[str] = None
    match_status: Optional[str] = None
    processing_status: Optional[str] = None


MATCH_RELEVANT_FIELDS = {"merchant_name", "receipt_date", "total_amount", "country"}


@router.patch("/{receipt_id}")
def patch_receipt(receipt_id: str, updates: ReceiptUpdate):
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
async def retry_receipt(receipt_id: str, background_tasks: BackgroundTasks):
    """Re-process a failed receipt extraction."""
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT image_url, file_type, processing_status FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Receipt not found")
    if row[2] not in ("failed", "completed"):
        raise HTTPException(status_code=400, detail=f"Receipt is {row[2]}, not retryable")

    # Reset extracted fields and status
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE receipts
                SET processing_status = 'pending',
                    merchant_name = NULL, receipt_date = NULL, subtotal = NULL,
                    tax_amount = NULL, tax_type = NULL, total_amount = NULL,
                    country = NULL, raw_ai_response = NULL,
                    transaction_id = NULL, match_status = 'unmatched'
                WHERE id = :id
            """),
            {"id": receipt_id},
        )

    logger.info(f"Retrying extraction for receipt {receipt_id}")
    background_tasks.add_task(_run_extraction_bg, receipt_id, row[0], row[1])
    return {"retrying": True, "receipt_id": receipt_id}


@router.post("/{receipt_id}/rematch")
def rematch_receipt(receipt_id: str):
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
def unmatch_receipt(receipt_id: str):
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
def delete_receipt(receipt_id: str):
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
            text("UPDATE transactions SET matched_receipt_id = NULL WHERE matched_receipt_id = :id"),
            {"id": receipt_id},
        )
        conn.execute(
            text("DELETE FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        )

    return {"deleted": True}
