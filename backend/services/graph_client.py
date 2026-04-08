import os
import logging
from datetime import datetime, timedelta, timezone
import httpx

logger = logging.getLogger("graph_client")

TENANT_ID = os.getenv("GRAPH_TENANT_ID")
CLIENT_ID = os.getenv("GRAPH_CLIENT_ID")
CLIENT_SECRET = os.getenv("GRAPH_CLIENT_SECRET")
MAILBOX = os.getenv("GRAPH_MAILBOX", "receipts@kotharigroup.com")

TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_token_cache = {"access_token": None, "expires_at": 0}


def get_access_token() -> str:
    """Client credentials token (application permissions). Cached until near expiry."""
    now = datetime.now(timezone.utc).timestamp()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    with httpx.Client(timeout=15) as client:
        resp = client.post(TOKEN_URL, data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        })
        resp.raise_for_status()
        data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = now + data.get("expires_in", 3600)
    logger.info("Graph access token acquired/refreshed")
    return _token_cache["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}"}


def create_subscription(notification_url: str, client_state: str) -> dict:
    """Create a Graph subscription for new messages in the mailbox Inbox."""
    expiration = datetime.now(timezone.utc) + timedelta(minutes=4230)  # ~2.9 days (max for mail)
    payload = {
        "changeType": "created",
        "notificationUrl": notification_url,
        "resource": f"users/{MAILBOX}/mailFolders/Inbox/messages",
        "expirationDateTime": expiration.strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
        "clientState": client_state,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{GRAPH_BASE}/subscriptions", json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

    logger.info(f"Subscription created: {data['id']} expires {data['expirationDateTime']}")
    return {
        "subscription_id": data["id"],
        "expiration_at": data["expirationDateTime"],
    }


def renew_subscription(subscription_id: str) -> dict:
    """Renew an existing subscription for another ~2.9 days."""
    expiration = datetime.now(timezone.utc) + timedelta(minutes=4230)
    payload = {
        "expirationDateTime": expiration.strftime("%Y-%m-%dT%H:%M:%S.0000000Z"),
    }
    with httpx.Client(timeout=30) as client:
        resp = client.patch(
            f"{GRAPH_BASE}/subscriptions/{subscription_id}",
            json=payload,
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    logger.info(f"Subscription renewed: {subscription_id} expires {data['expirationDateTime']}")
    return {
        "subscription_id": data["id"],
        "expiration_at": data["expirationDateTime"],
    }


def delete_subscription(subscription_id: str):
    """Delete a subscription (cleanup)."""
    with httpx.Client(timeout=15) as client:
        resp = client.delete(
            f"{GRAPH_BASE}/subscriptions/{subscription_id}",
            headers=_headers(),
        )
        if resp.status_code == 404:
            logger.info(f"Subscription {subscription_id} already gone")
            return
        resp.raise_for_status()
    logger.info(f"Subscription deleted: {subscription_id}")


def fetch_message(message_id: str) -> dict:
    """Fetch message metadata (subject, from, receivedDateTime)."""
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{GRAPH_BASE}/users/{MAILBOX}/messages/{message_id}",
            params={"$select": "id,subject,from,receivedDateTime,hasAttachments"},
            headers=_headers(),
        )
        resp.raise_for_status()
    return resp.json()


def fetch_attachments(message_id: str) -> list[dict]:
    """
    Fetch all attachments for a message.
    Returns list of {name, content_type, content_bytes}.
    """
    with httpx.Client(timeout=60) as client:
        resp = client.get(
            f"{GRAPH_BASE}/users/{MAILBOX}/messages/{message_id}/attachments",
            params={"$select": "id,name,contentType,contentBytes,isInline,contentId"},
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()

    import base64
    results = []
    for att in data.get("value", []):
        content_b64 = att.get("contentBytes")
        if not content_b64:
            continue
        results.append({
            "name": att.get("name", "attachment"),
            "content_type": att.get("contentType", "application/octet-stream"),
            "content_bytes": base64.b64decode(content_b64),
            "is_inline": att.get("isInline", False),
            "content_id": att.get("contentId"),
        })

    logger.info(f"Fetched {len(results)} attachments for message {message_id}")
    return results
