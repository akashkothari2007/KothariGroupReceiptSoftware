"""
Write match results to the database.

apply_match(tx_id, receipt_id, match_status, match_method)
  - Links receipt to transaction (matched_receipt_id)
  - Updates match_status on both transaction and receipt
  - Auto-fills tax_amount on transaction based on country rule:
      Canadian receipt (HST/GST/PST) → copy tax from receipt
      Foreign or no tax → set tax to 0

This is a standalone function so it can be called from:
  - The auto-matching engine (after scoring)
  - Manual matching (user picks a receipt for a transaction)
"""

import logging
from sqlalchemy import text
from db import engine

logger = logging.getLogger("match_writer")

CANADIAN_TAX_TYPES = {"HST", "GST", "PST", "GST+PST", "GST+QST"}


def apply_match(transaction_id: str, receipt_id: str, match_status: str, match_method: str):
    """Link a receipt to a transaction and auto-fill tax.

    Args:
        transaction_id: UUID of the transaction
        receipt_id: UUID of the receipt
        match_status: 'matched_sure' or 'matched_unsure'
        match_method: how the match was made, e.g. 'auto', 'manual'
    """
    logger.info(f"Applying match: tx={transaction_id} ↔ receipt={receipt_id} status={match_status} method={match_method}")

    with engine.begin() as conn:
        # ── Bidirectional cleanup: clear any stale matches first ──
        # If this tx already has a different receipt, clear that receipt's link
        old_receipt = conn.execute(
            text("SELECT matched_receipt_id FROM transactions WHERE id = :tid"),
            {"tid": transaction_id},
        ).fetchone()
        if old_receipt and old_receipt[0] and str(old_receipt[0]) != receipt_id:
            old_rid = str(old_receipt[0])
            logger.info(f"  Clearing stale receipt {old_rid} from tx={transaction_id}")
            conn.execute(
                text("UPDATE receipts SET transaction_id = NULL, match_status = 'unmatched' WHERE id = :rid"),
                {"rid": old_rid},
            )

        # If this receipt already has a different tx, clear that tx's link
        old_tx = conn.execute(
            text("SELECT transaction_id FROM receipts WHERE id = :rid"),
            {"rid": receipt_id},
        ).fetchone()
        if old_tx and old_tx[0] and str(old_tx[0]) != transaction_id:
            old_tid = str(old_tx[0])
            logger.info(f"  Clearing stale tx {old_tid} from receipt={receipt_id}")
            conn.execute(
                text("UPDATE transactions SET matched_receipt_id = NULL, match_status = 'unmatched', tax_amount = NULL WHERE id = :tid"),
                {"tid": old_tid},
            )

        # Fetch receipt details for tax logic
        r = conn.execute(
            text("SELECT tax_amount, tax_type, country FROM receipts WHERE id = :id"),
            {"id": receipt_id},
        ).fetchone()

        if not r:
            logger.error(f"Receipt {receipt_id} not found, skipping match")
            return False

        receipt_tax = float(r[0]) if r[0] is not None else None
        receipt_tax_type = r[1]
        receipt_country = (r[2] or "").strip().upper()

        # Determine tax for the transaction
        is_canadian_tax = (
            receipt_tax_type is not None
            and receipt_tax_type.upper() in CANADIAN_TAX_TYPES
        )

        if is_canadian_tax and receipt_tax is not None:
            tx_tax = receipt_tax
            logger.info(f"  Canadian tax: {receipt_tax_type} ${receipt_tax:.2f} → copying to transaction")
        else:
            tx_tax = 0.0
            reason = f"foreign country={receipt_country}" if receipt_country and receipt_country != "CA" else f"tax_type={receipt_tax_type}"
            logger.info(f"  Non-claimable tax ({reason}) → setting tx tax to $0.00")

        # Update transaction: link receipt, set match_status, fill tax
        conn.execute(
            text("""
                UPDATE transactions
                SET matched_receipt_id = :rid,
                    match_status = :status,
                    tax_amount = :tax
                WHERE id = :tid
            """),
            {
                "tid": transaction_id,
                "rid": receipt_id,
                "status": match_status,
                "tax": tx_tax,
            },
        )

        # Update receipt: link transaction, set match_status
        conn.execute(
            text("""
                UPDATE receipts
                SET transaction_id = :tid,
                    match_status = :status
                WHERE id = :rid
            """),
            {
                "rid": receipt_id,
                "tid": transaction_id,
                "status": match_status,
            },
        )

    logger.info(f"Match applied: tx={transaction_id} ↔ receipt={receipt_id} (tax=${tx_tax:.2f})")
    return True


def remove_match(transaction_id: str):
    """Unlink a receipt from a transaction. Resets both sides."""
    logger.info(f"Removing match from tx={transaction_id}")

    with engine.begin() as conn:
        # Find the currently linked receipt
        row = conn.execute(
            text("SELECT matched_receipt_id FROM transactions WHERE id = :tid"),
            {"tid": transaction_id},
        ).fetchone()

        if not row or not row[0]:
            logger.info(f"  No match to remove on tx={transaction_id}")
            return False

        receipt_id = str(row[0])

        # Reset transaction
        conn.execute(
            text("""
                UPDATE transactions
                SET matched_receipt_id = NULL,
                    match_status = 'unmatched',
                    tax_amount = NULL
                WHERE id = :tid
            """),
            {"tid": transaction_id},
        )

        # Reset receipt
        conn.execute(
            text("""
                UPDATE receipts
                SET transaction_id = NULL,
                    match_status = 'unmatched'
                WHERE id = :rid
            """),
            {"rid": receipt_id},
        )

    logger.info(f"Match removed: tx={transaction_id} ↔ receipt={receipt_id}")
    return True
