import os
import asyncio
import logging
import threading
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import text
from db import engine
from services.graph_client import (
    create_subscription,
    renew_subscription,
    delete_subscription,
    fetch_message,
    fetch_attachments,
)
from services.email_triage import pick_receipt_candidates
from services.receipt_ingest import ingest_receipt_bytes

logger = logging.getLogger("graph_webhook")

router = APIRouter(prefix="/graph", tags=["graph"])

WEBHOOK_SECRET = os.getenv("GRAPH_WEBHOOK_SECRET", "")
BACKEND_URL = os.getenv("BACKEND_URL", "")


@router.post("/webhook")
async def graph_webhook(request: Request):
    """
    Receives Graph change notifications.
    - Validation handshake: return validationToken as plain text.
    - Real notification: validate clientState, ACK fast, process in background.
    """
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        logger.info("Graph subscription validation handshake")
        return PlainTextResponse(content=validation_token)

    body = await request.json()

    for notification in body.get("value", []):
        client_state = notification.get("clientState", "")
        if client_state != WEBHOOK_SECRET:
            logger.warning(f"Invalid clientState: {client_state}")
            continue

        resource = notification.get("resource", "")
        # resource looks like: users/receipts@.../messages/AAMk...
        parts = resource.split("/messages/")
        if len(parts) < 2:
            logger.warning(f"Unexpected resource format: {resource}")
            continue

        message_id = parts[1]
        logger.info(f"Notification for message: {message_id}")

        threading.Thread(
            target=_process_email_sync,
            args=(message_id,),
            daemon=True,
        ).start()

    return PlainTextResponse(content="", status_code=202)


def _process_email_sync(message_id: str):
    """Sync wrapper for async processing."""
    try:
        asyncio.run(_process_email(message_id))
    except Exception as e:
        logger.error(f"Email processing failed for {message_id}: {e}", exc_info=True)


async def _process_email(message_id: str):
    """Fetch email, triage attachments, ingest receipts."""

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM processed_emails WHERE message_id = :mid"),
            {"mid": message_id},
        ).fetchone()
    if exists:
        logger.info(f"Message {message_id} already processed, skipping")
        return

    msg = fetch_message(message_id)
    sender = msg.get("from", {}).get("emailAddress", {}).get("address", "unknown")
    received_at = msg.get("receivedDateTime")
    subject = msg.get("subject", "(no subject)")
    logger.info(f"Processing email: '{subject}' from {sender}")

    attachments = fetch_attachments(message_id)
    if not attachments:
        logger.info(f"No attachments in message {message_id}, skipping")
        _mark_processed(message_id)
        return

    candidates = await pick_receipt_candidates(attachments)
    if not candidates:
        logger.info(f"No receipt candidates found in message {message_id}")
        _mark_processed(message_id)
        return

    for candidate in candidates:
        try:
            result = ingest_receipt_bytes(
                file_bytes=candidate["content_bytes"],
                filename=candidate["name"],
                content_type=candidate["content_type"],
                source="email",
                email_message_id=message_id,
                email_sender=sender,
                email_received_at=received_at,
            )
            logger.info(f"Ingested receipt {result['id']} from email {message_id}")
        except Exception as e:
            logger.error(f"Failed to ingest attachment '{candidate['name']}' from {message_id}: {e}", exc_info=True)

    _mark_processed(message_id)


def _mark_processed(message_id: str):
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO processed_emails (message_id) VALUES (:mid) ON CONFLICT DO NOTHING"),
            {"mid": message_id},
        )


@router.post("/subscription/ensure")
def ensure_subscription(request: Request):
    """
    Create or renew the Graph mail subscription.
    Protected by webhook secret header.
    """
    auth = request.headers.get("X-Webhook-Secret", "")
    if auth != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    notification_url = BACKEND_URL.rstrip("/") + "/graph/webhook"

    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, subscription_id, expiration_at, status
                FROM email_subscription_state
                WHERE status = 'active'
                ORDER BY updated_at DESC
                LIMIT 1
            """)
        ).fetchone()

    if row:
        sub_id = row[1]
        expiration = row[2]
        now = datetime.now(timezone.utc)

        if expiration and expiration.tzinfo is None:
            from datetime import timezone as tz
            expiration = expiration.replace(tzinfo=tz.utc)

        hours_left = (expiration - now).total_seconds() / 3600 if expiration else 0

        if hours_left > 12:
            logger.info(f"Subscription {sub_id} still valid ({hours_left:.1f}h left)")
            return {"action": "none", "subscription_id": sub_id, "hours_left": round(hours_left, 1)}

        try:
            result = renew_subscription(sub_id)
            _update_subscription_state(row[0], result["subscription_id"], result["expiration_at"], "active")
            return {"action": "renewed", "subscription_id": result["subscription_id"]}
        except Exception as e:
            logger.warning(f"Renewal failed for {sub_id}, will recreate: {e}")
            try:
                delete_subscription(sub_id)
            except Exception:
                pass
            _update_subscription_state(row[0], sub_id, None, "expired")

    try:
        result = create_subscription(notification_url, WEBHOOK_SECRET)
        _insert_subscription_state(result["subscription_id"], result["expiration_at"])
        return {"action": "created", "subscription_id": result["subscription_id"]}
    except Exception as e:
        logger.error(f"Subscription creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create subscription: {str(e)}")


def _insert_subscription_state(subscription_id: str, expiration_at: str):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO email_subscription_state (subscription_id, expiration_at, client_state, status, updated_at)
                VALUES (:sid, :exp, :cs, 'active', now())
            """),
            {"sid": subscription_id, "exp": expiration_at, "cs": WEBHOOK_SECRET},
        )


def _update_subscription_state(row_id: int, subscription_id: str, expiration_at, status: str):
    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE email_subscription_state
                SET subscription_id = :sid, expiration_at = :exp, status = :status, updated_at = now()
                WHERE id = :id
            """),
            {"sid": subscription_id, "exp": expiration_at, "status": status, "id": row_id},
        )
