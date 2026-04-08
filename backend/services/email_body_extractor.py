import re
import logging
from html.parser import HTMLParser

from services.ai import call_azure_text
from services.prompts import EMAIL_BODY_RECEIPT_PROMPT

logger = logging.getLogger("email_body_extractor")

MAX_BODY_CHARS = 6000


class _HTMLStripper(HTMLParser):
    """Strips HTML tags, keeping only visible text."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def strip_html(html: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(html)
    text = stripper.get_text()
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def extract_receipt_from_body(html_body: str) -> dict | None:
    """
    Strips HTML to plain text, sends to AI for triage + extraction in one call.
    Returns extracted fields dict if a receipt is found, None otherwise.
    """
    plain_text = strip_html(html_body)
    if len(plain_text) < 30:
        logger.info(f"Email body too short ({len(plain_text)} chars), skipping")
        return None

    truncated = plain_text[:MAX_BODY_CHARS]
    prompt = EMAIL_BODY_RECEIPT_PROMPT + truncated

    try:
        result = await call_azure_text(prompt)
    except Exception as e:
        logger.error(f"AI body extraction failed: {e}", exc_info=True)
        return None

    if not result.get("is_receipt"):
        logger.info("AI determined email body is not a receipt")
        return None

    logger.info(f"AI extracted receipt from email body: merchant={result.get('merchant_name')}, total={result.get('total_amount')}")
    return result
