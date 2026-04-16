import uuid
import os
import re
import json
import asyncio
import logging
import threading
from typing import Optional
from sqlalchemy import text
from supabase import create_client
from db import engine
from services.receipt_extractor import extract_receipt_data, update_receipt
from services.match_run import run_matching_for_receipt
from services.email_body_extractor import extract_receipt_from_body

logger = logging.getLogger("receipt_ingest")

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf", "image/heic", "image/heif", "text/html"}
BUCKET = "receipts"

_supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def _run_extraction_bg(receipt_id: str, storage_path: str, file_type: str):
    asyncio.run(extract_receipt_data(receipt_id, storage_path, file_type, _supabase))


def _run_email_body_extraction_bg(receipt_id: str, storage_path: str):
    """Background re-extraction path for HTML receipts ingested from email bodies."""
    update_receipt(receipt_id, {"processing_status": "processing"})

    try:
        file_bytes = _supabase.storage.from_(BUCKET).download(storage_path)
        html_body = file_bytes.decode("utf-8", errors="ignore")
        extracted = asyncio.run(extract_receipt_from_body(html_body))

        if not extracted:
            update_receipt(
                receipt_id,
                {
                    "processing_status": "failed",
                    "raw_ai_response": json.dumps({"error": "No receipt found in email body"}),
                },
            )
            return

        field_map = {
            "merchant_name": "merchant_name",
            "receipt_date": "receipt_date",
            "subtotal": "subtotal",
            "tax_amount": "tax_amount",
            "tax_type": "tax_type",
            "total_amount": "total_amount",
            "country": "country",
            "city": "city",
            "province": "province",
        }
        fields = {
            "raw_ai_response": json.dumps(extracted),
            "processing_status": "completed",
        }
        for ai_key, db_key in field_map.items():
            val = extracted.get(ai_key)
            if val is not None and val != "null" and val != "":
                fields[db_key] = val

        is_refund = extracted.get("is_refund")
        if is_refund is True and fields.get("total_amount") is not None:
            try:
                amt = float(fields["total_amount"])
                if amt > 0:
                    fields["total_amount"] = -amt
            except (ValueError, TypeError):
                pass

        update_receipt(receipt_id, fields)
        run_matching_for_receipt(receipt_id)
    except Exception as e:
        logger.error(f"[{receipt_id}] Email body retry extraction failed: {e}", exc_info=True)
        update_receipt(
            receipt_id,
            {
                "processing_status": "failed",
                "raw_ai_response": json.dumps({"error": str(e)}),
            },
        )


def ingest_receipt_bytes(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    source: str = "manual",
    email_message_id: Optional[str] = None,
    email_sender: Optional[str] = None,
    email_received_at: Optional[str] = None,
    extracted_fields: Optional[dict] = None,
) -> dict:
    """
    Shared receipt ingestion: store file, create DB row, queue extraction.
    If extracted_fields is provided (e.g. from email body AI), skip background
    extraction and write the fields directly.
    Returns the receipt dict. Raises on failure.
    """
    if content_type not in ALLOWED_TYPES:
        raise ValueError(f"File type '{content_type}' not allowed.")

    safe_name = re.sub(r'[^\w.\-]', '_', filename)
    storage_filename = f"{uuid.uuid4()}_{safe_name}"

    _supabase.storage.from_(BUCKET).upload(
        path=storage_filename,
        file=file_bytes,
        file_options={"content-type": content_type},
    )
    logger.info(f"Stored {storage_filename} in Supabase Storage")

    processing_status = "completed" if extracted_fields else "pending"

    insert_sql = """
        INSERT INTO receipts (
            image_url, file_type, file_name, source, processing_status,
            email_message_id, email_sender, email_received_at
        ) VALUES (
            :image_url, :file_type, :file_name, :source, :processing_status,
            :email_message_id, :email_sender, :email_received_at
        )
        RETURNING id, image_url, file_name, file_type, source,
                  match_status, processing_status, created_at
    """
    params = {
        "image_url": storage_filename,
        "file_type": content_type,
        "file_name": filename,
        "source": source,
        "processing_status": processing_status,
        "email_message_id": email_message_id,
        "email_sender": email_sender,
        "email_received_at": email_received_at,
    }

    with engine.begin() as conn:
        row = conn.execute(text(insert_sql), params).fetchone()

    receipt_id = str(row[0])
    logger.info(f"Receipt created: {receipt_id} — {filename} ({content_type}) source={source}")

    if extracted_fields:
        _apply_preextracted_fields(receipt_id, extracted_fields)
    else:
        threading.Thread(
            target=_run_extraction_bg,
            args=(receipt_id, storage_filename, content_type),
            daemon=True,
        ).start()

    return {
        "id": receipt_id,
        "image_url": row[1],
        "file_name": row[2],
        "file_type": row[3],
        "source": row[4],
        "match_status": row[5],
        "processing_status": row[6],
        "merchant_name": extracted_fields.get("merchant_name") if extracted_fields else None,
        "receipt_date": extracted_fields.get("receipt_date") if extracted_fields else None,
        "tax_amount": extracted_fields.get("tax_amount") if extracted_fields else None,
        "tax_type": extracted_fields.get("tax_type") if extracted_fields else None,
        "total_amount": extracted_fields.get("total_amount") if extracted_fields else None,
        "created_at": str(row[7]),
    }


def _apply_preextracted_fields(receipt_id: str, extracted: dict):
    """Write pre-extracted AI fields to the receipt row and trigger matching."""
    field_map = {
        "merchant_name": "merchant_name",
        "receipt_date": "receipt_date",
        "subtotal": "subtotal",
        "tax_amount": "tax_amount",
        "tax_type": "tax_type",
        "total_amount": "total_amount",
        "country": "country",
        "city": "city",
        "province": "province",
    }

    fields = {
        "raw_ai_response": json.dumps(extracted),
        "processing_status": "completed",
    }

    for ai_key, db_key in field_map.items():
        val = extracted.get(ai_key)
        if val is not None and val != "null" and val != "":
            fields[db_key] = val

    is_refund = extracted.get("is_refund")
    if is_refund is True and fields.get("total_amount") is not None:
        try:
            amt = float(fields["total_amount"])
            if amt > 0:
                fields["total_amount"] = -amt
                logger.info(f"[{receipt_id}] Refund detected — negated total to {-amt}")
        except (ValueError, TypeError):
            pass

    update_receipt(receipt_id, fields)
    logger.info(f"[{receipt_id}] Pre-extracted fields written")

    try:
        matches = run_matching_for_receipt(receipt_id)
        logger.info(f"[{receipt_id}] Auto-matching found {len(matches)} match(es)")
    except Exception as me:
        logger.error(f"[{receipt_id}] Auto-matching failed: {me}", exc_info=True)
