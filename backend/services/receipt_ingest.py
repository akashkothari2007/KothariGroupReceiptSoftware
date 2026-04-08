import uuid
import os
import re
import asyncio
import logging
import threading
from typing import Optional
from sqlalchemy import text
from supabase import create_client
from db import engine
from services.receipt_extractor import extract_receipt_data

logger = logging.getLogger("receipt_ingest")

ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf", "image/heic", "image/heif"}
BUCKET = "receipts"

_supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def _run_extraction_bg(receipt_id: str, storage_path: str, file_type: str):
    asyncio.run(extract_receipt_data(receipt_id, storage_path, file_type, _supabase))


def ingest_receipt_bytes(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    source: str = "manual",
    email_message_id: Optional[str] = None,
    email_sender: Optional[str] = None,
    email_received_at: Optional[str] = None,
) -> dict:
    """
    Shared receipt ingestion: store file, create DB row, queue extraction.
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

    insert_sql = """
        INSERT INTO receipts (
            image_url, file_type, file_name, source, processing_status,
            email_message_id, email_sender, email_received_at
        ) VALUES (
            :image_url, :file_type, :file_name, :source, 'pending',
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
        "email_message_id": email_message_id,
        "email_sender": email_sender,
        "email_received_at": email_received_at,
    }

    with engine.begin() as conn:
        row = conn.execute(text(insert_sql), params).fetchone()

    receipt_id = str(row[0])
    logger.info(f"Receipt created: {receipt_id} — {filename} ({content_type}) source={source}")

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
        "merchant_name": None,
        "receipt_date": None,
        "tax_amount": None,
        "tax_type": None,
        "total_amount": None,
        "created_at": str(row[7]),
    }
