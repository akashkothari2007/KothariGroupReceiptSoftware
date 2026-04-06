import uuid
import os
import re
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import text
from supabase import create_client
from db import engine
from services.receipt_extractor import extract_receipt_data

logger = logging.getLogger("receipts")
router = APIRouter(prefix="/receipts", tags=["receipts"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf", "image/heic", "image/heif"}
BUCKET = "receipts"

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def _run_extraction_bg(receipt_id: str, storage_path: str, file_type: str):
    """Wrapper to run async extraction from a sync BackgroundTask."""
    asyncio.run(extract_receipt_data(receipt_id, storage_path, file_type, supabase))


@router.post("/upload")
async def upload_receipt(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    logger.info(f"Upload request: filename={file.filename}, content_type={file.content_type}, size={file.size}")

    if file.content_type not in ALLOWED_TYPES:
        logger.warning(f"Rejected file type: {file.content_type} for {file.filename}")
        raise HTTPException(status_code=400, detail=f"File type '{file.content_type}' not allowed. Use JPEG, PNG, PDF, or HEIC.")

    contents = await file.read()
    logger.info(f"Read {len(contents)} bytes from {file.filename}")
    # Sanitize filename — Supabase rejects special Unicode chars (e.g. narrow no-break space in macOS screenshots)
    safe_name = re.sub(r'[^\w.\-]', '_', file.filename)
    storage_filename = f"{uuid.uuid4()}_{safe_name}"

    # Upload to Supabase Storage
    try:
        supabase.storage.from_(BUCKET).upload(
            path=storage_filename,
            file=contents,
            file_options={"content-type": file.content_type},
        )
        logger.info(f"Stored {storage_filename} in Supabase Storage")
    except Exception as e:
        logger.error(f"Storage upload failed for {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e)}")

    # Insert row into receipts table
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO receipts (image_url, file_type, file_name, source, processing_status)
                VALUES (:image_url, :file_type, :file_name, 'manual', 'pending')
                RETURNING id, image_url, file_name, file_type, source, match_status, processing_status, created_at
            """),
            {
                "image_url": storage_filename,
                "file_type": file.content_type,
                "file_name": file.filename,
            },
        )
        row = result.fetchone()

    receipt_id = str(row[0])
    logger.info(f"Receipt created: {receipt_id} — {file.filename} ({file.content_type})")

    # Kick off AI extraction in background
    background_tasks.add_task(_run_extraction_bg, receipt_id, storage_filename, file.content_type)
    logger.info(f"Background extraction queued for {receipt_id}")

    return {
        "id": receipt_id,
        "image_url": row[1],
        "file_name": row[2],
        "file_type": row[3],
        "source": row[4],
        "match_status": row[5],
        "processing_status": row[6],
        "merchant_name": None,
        "receipt_date": None,
        "tax_amount": None,
        "tax_type": None,
        "total_amount": None,
        "created_at": str(row[7]),
    }


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


@router.patch("/{receipt_id}")
def patch_receipt(receipt_id: str, updates: ReceiptUpdate):
    fields = {k: v for k, v in updates.model_dump().items() if v is not None and k in RECEIPT_ALLOWED_FIELDS}
    if not fields:
        return {"updated": False}

    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Receipt not found")

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

    return {"updated": True}


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
