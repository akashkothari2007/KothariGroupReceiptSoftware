import io
import json
import logging
import fitz  # pymupdf
from PIL import Image
import pillow_heif
pillow_heif.register_heif_opener()
from sqlalchemy import text
from db import engine
from services.ai import call_azure_vision
from services.prompts import RECEIPT_EXTRACTION_PROMPT
from services.match_run import run_matching_for_receipt

logger = logging.getLogger("receipt_extractor")


def pdf_first_page_to_png(pdf_bytes: bytes) -> bytes:
    """Convert first page of a PDF to PNG bytes."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(dpi=200)
    png_bytes = pix.tobytes("png")
    doc.close()
    return png_bytes


def heic_to_png(heic_bytes: bytes) -> bytes:
    """Convert HEIC/HEIF image to PNG bytes."""
    img = Image.open(io.BytesIO(heic_bytes))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def update_receipt(receipt_id: str, fields: dict):
    """Patch a receipt row. No-op if receipt was deleted."""
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()
        if not exists:
            return False

        params = {"rid": receipt_id}
        set_parts = []
        for k, v in fields.items():
            if v is None:
                set_parts.append(f"{k} = NULL")
            else:
                set_parts.append(f"{k} = :{k}")
                params[k] = v

        if set_parts:
            query = f"UPDATE receipts SET {', '.join(set_parts)} WHERE id = :rid"
            conn.execute(text(query), params)
        return True


async def extract_receipt_data(receipt_id: str, storage_path: str, file_type: str, supabase_client):
    """
    Background task: download file from storage, run vision AI, update receipt.
    """
    logger.info(f"[{receipt_id}] Starting extraction — path={storage_path}, type={file_type}")

    # Mark as processing
    update_receipt(receipt_id, {"processing_status": "processing"})

    try:
        # Download file from Supabase Storage
        logger.info(f"[{receipt_id}] Downloading from storage...")
        file_bytes = supabase_client.storage.from_("receipts").download(storage_path)
        logger.info(f"[{receipt_id}] Downloaded {len(file_bytes)} bytes")

        # Convert to PNG if needed
        if file_type == "application/pdf":
            logger.info(f"[{receipt_id}] Converting PDF to PNG...")
            image_bytes = pdf_first_page_to_png(file_bytes)
            mime_type = "image/png"
            logger.info(f"[{receipt_id}] PDF converted — {len(image_bytes)} bytes")
        elif file_type in ("image/heic", "image/heif"):
            logger.info(f"[{receipt_id}] Converting HEIC to PNG...")
            image_bytes = heic_to_png(file_bytes)
            mime_type = "image/png"
            logger.info(f"[{receipt_id}] HEIC converted — {len(image_bytes)} bytes")
        else:
            image_bytes = file_bytes
            mime_type = file_type

        # Call Azure Vision
        logger.info(f"[{receipt_id}] Calling Azure vision...")
        result = await call_azure_vision(image_bytes, RECEIPT_EXTRACTION_PROMPT, mime_type)
        logger.info(f"[{receipt_id}] AI extraction complete: {result}")

        # Build update fields
        fields = {
            "raw_ai_response": json.dumps(result),
            "processing_status": "completed",
        }

        field_map = {
            "merchant_name": "merchant_name",
            "receipt_date": "receipt_date",
            "subtotal": "subtotal",
            "tax_amount": "tax_amount",
            "tax_type": "tax_type",
            "total_amount": "total_amount",
            "country": "country",
        }

        for ai_key, db_key in field_map.items():
            val = result.get(ai_key)
            if val is not None and val != "null" and val != "":
                fields[db_key] = val

        updated = update_receipt(receipt_id, fields)
        if updated:
            logger.info(f"[{receipt_id}] Receipt updated successfully")
            # Try auto-matching now that extraction is done
            try:
                matches = run_matching_for_receipt(receipt_id)
                logger.info(f"[{receipt_id}] Auto-matching found {len(matches)} match(es)")
            except Exception as me:
                logger.error(f"[{receipt_id}] Auto-matching failed: {me}", exc_info=True)
        else:
            logger.warning(f"[{receipt_id}] Receipt was deleted before update")

    except Exception as e:
        logger.error(f"[{receipt_id}] Extraction failed: {e}", exc_info=True)
        update_receipt(receipt_id, {
            "processing_status": "failed",
            "raw_ai_response": json.dumps({"error": str(e)}),
        })
