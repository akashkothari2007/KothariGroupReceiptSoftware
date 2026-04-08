import io
import base64
import logging
from PIL import Image
from services.ai import call_azure_vision

logger = logging.getLogger("email_triage")

RECEIPT_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf", "image/heic", "image/heif"}

TRIAGE_PROMPT = """You are an email attachment classifier. You will see one or more images from an email's attachments and inline images.

Your job: decide which image(s) are actual receipts, invoices, or purchase confirmations.

Ignore: company logos, email signatures, banners, marketing images, social media icons, tracking pixels, app store badges.

Return ONLY valid JSON — an array of objects:
[
  {"index": 0, "is_receipt": true, "reason": "hotel invoice with total"},
  {"index": 1, "is_receipt": false, "reason": "company logo"}
]

Rules:
- index matches the order of images provided (0-based)
- Be strict: only mark as receipt if it clearly shows a purchase amount or itemized charges
- Return ONLY the JSON array, no markdown, no explanation
"""


def _make_thumbnail(image_bytes: bytes, content_type: str, max_size: int = 512) -> bytes:
    """Downscale an image to save tokens on the triage call."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((max_size, max_size))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return image_bytes


def _heuristic_filter(candidates: list[dict]) -> list[dict]:
    """Fallback: keep candidates with receipt-like names or PDF/image types."""
    receipt_keywords = {"receipt", "invoice", "order", "confirmation", "tax", "bill", "statement"}
    results = []
    for c in candidates:
        name_lower = (c.get("name") or "").lower()
        if c["content_type"] in RECEIPT_MIME_TYPES:
            if any(kw in name_lower for kw in receipt_keywords):
                results.append(c)
            elif c["content_type"] == "application/pdf":
                results.append(c)
            elif not c.get("is_inline"):
                results.append(c)
    return results


async def pick_receipt_candidates(candidates: list[dict]) -> list[dict]:
    """
    Given a list of email attachment dicts (name, content_type, content_bytes, is_inline),
    use one cheap AI call to pick which ones are actual receipts.
    Falls back to heuristic if AI fails.
    Returns the subset of candidates that are receipts.
    """
    image_candidates = [c for c in candidates if c["content_type"] in RECEIPT_MIME_TYPES]
    if not image_candidates:
        return []

    if len(image_candidates) == 1:
        c = image_candidates[0]
        if c.get("is_inline") and len(c.get("content_bytes", b"")) < 5000:
            return []
        return image_candidates

    thumbnails = []
    for c in image_candidates:
        if c["content_type"] == "application/pdf":
            from services.receipt_extractor import pdf_to_pngs
            try:
                pages = pdf_to_pngs(c["content_bytes"], max_pages=1)
                thumbnails.append(_make_thumbnail(pages[0], "image/png"))
            except Exception:
                thumbnails.append(None)
        else:
            thumbnails.append(_make_thumbnail(c["content_bytes"], c["content_type"]))

    valid_thumbs = [(i, t) for i, t in enumerate(thumbnails) if t is not None]
    if not valid_thumbs:
        return _heuristic_filter(image_candidates)

    try:
        all_thumb_bytes = [t for _, t in valid_thumbs]
        result = await call_azure_vision(all_thumb_bytes, TRIAGE_PROMPT, "image/png")

        if not isinstance(result, list):
            logger.warning(f"Triage AI returned non-list: {result}")
            return _heuristic_filter(image_candidates)

        selected = []
        for item in result:
            idx = item.get("index")
            if item.get("is_receipt") and idx is not None and idx < len(valid_thumbs):
                original_idx = valid_thumbs[idx][0]
                selected.append(image_candidates[original_idx])

        logger.info(f"AI triage: {len(selected)}/{len(image_candidates)} candidates selected as receipts")
        return selected if selected else _heuristic_filter(image_candidates)

    except Exception as e:
        logger.error(f"AI triage failed, using heuristic: {e}", exc_info=True)
        return _heuristic_filter(image_candidates)
