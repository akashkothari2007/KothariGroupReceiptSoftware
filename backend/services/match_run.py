"""
Fetch unmatched transactions + receipts, run the matcher, write results.

run_matching_for_statement(statement_id)
  - Fetches unmatched transactions for that statement
  - Also fetches unsure-matched receipts for re-evaluation
  - Runs the scoring engine
  - Writes/upgrades matches to DB

run_matching_for_receipt(receipt_id)
  - Fetches unmatched transactions from all statements
  - Also fetches unsure-matched transactions for re-evaluation
  - Runs the scoring engine against just this receipt
  - Writes/upgrades match to DB if found
"""

import logging
from sqlalchemy import text
from db import engine
from services.matcher import run_matching
from services.match_writer import apply_match, remove_match

logger = logging.getLogger("match_run")


def _tx_row_to_dict(r) -> dict:
    return {
        "id": str(r[0]),
        "transaction_date": r[1].isoformat() if r[1] else None,
        "merchant": r[2],
        "description": r[3],
        "amount_cad": float(r[4]) if r[4] is not None else None,
        "foreign_amount": float(r[5]) if r[5] is not None else None,
        "foreign_currency": r[6],
        "match_status": r[7],
        "matched_receipt_id": str(r[8]) if r[8] else None,
    }


def _receipt_row_to_dict(r) -> dict:
    return {
        "id": str(r[0]),
        "merchant_name": r[1],
        "receipt_date": r[2].isoformat() if r[2] else None,
        "total_amount": float(r[3]) if r[3] is not None else None,
        "tax_amount": float(r[4]) if r[4] is not None else None,
        "tax_type": r[5],
        "country": r[6],
        "match_status": r[7],
        "transaction_id": str(r[8]) if r[8] else None,
    }


_TX_COLS = """id, transaction_date, merchant, description,
              amount_cad, foreign_amount, foreign_currency,
              match_status, matched_receipt_id"""

_RECEIPT_COLS = """id, merchant_name, receipt_date, total_amount,
                   tax_amount, tax_type, country, match_status,
                   transaction_id"""


def run_matching_for_statement(statement_id: str) -> list:
    """Run matching for all unmatched transactions in a statement.
    Also re-evaluates unsure-matched receipts in case a better match exists."""
    logger.info(f"Running matching for statement {statement_id}")

    with engine.connect() as conn:
        # Unmatched transactions from this statement
        tx_rows = conn.execute(
            text(f"""
                SELECT {_TX_COLS} FROM transactions
                WHERE statement_id = :sid AND matched_receipt_id IS NULL
            """),
            {"sid": statement_id},
        ).fetchall()
        transactions = [_tx_row_to_dict(r) for r in tx_rows]

        # Unmatched receipts + unsure-matched receipts (eligible for upgrade)
        r_rows = conn.execute(
            text(f"""
                SELECT {_RECEIPT_COLS} FROM receipts
                WHERE processing_status = 'completed'
                  AND (transaction_id IS NULL OR match_status = 'matched_unsure')
            """)
        ).fetchall()
        receipts = [_receipt_row_to_dict(r) for r in r_rows]

    logger.info(f"Found {len(transactions)} unmatched tx, {len(receipts)} candidate receipts (incl unsure)")

    matches = run_matching(transactions, receipts)
    applied = _apply_matches(matches, receipts)

    logger.info(f"Statement {statement_id}: {applied} matches applied/upgraded")
    return matches


def run_matching_for_receipt(receipt_id: str) -> list:
    """Run matching for a single newly-completed receipt against all transactions.
    Also considers unsure-matched transactions that might be a better fit."""
    logger.info(f"Running matching for receipt {receipt_id}")

    with engine.connect() as conn:
        row = conn.execute(
            text(f"""
                SELECT {_RECEIPT_COLS} FROM receipts
                WHERE id = :rid AND processing_status = 'completed'
            """),
            {"rid": receipt_id},
        ).fetchone()

        if not row:
            logger.info(f"Receipt {receipt_id} not found or not completed, skipping")
            return []

        receipt = _receipt_row_to_dict(row)

        if receipt["transaction_id"] and receipt["match_status"] != "matched_unsure":
            logger.info(f"Receipt {receipt_id} already matched (sure), skipping")
            return []

        # Unmatched tx + unsure-matched tx (eligible for upgrade)
        tx_rows = conn.execute(
            text(f"""
                SELECT {_TX_COLS} FROM transactions
                WHERE matched_receipt_id IS NULL
                   OR match_status = 'matched_unsure'
            """)
        ).fetchall()
        transactions = [_tx_row_to_dict(r) for r in tx_rows]

    logger.info(f"Matching receipt against {len(transactions)} candidate tx (incl unsure)")

    matches = run_matching(transactions, [receipt])
    applied = _apply_matches(matches, [receipt])

    logger.info(f"Receipt {receipt_id}: {applied} matches applied/upgraded")
    return matches


def _apply_matches(matches: list, receipts_pool: list) -> int:
    """Apply match results, handling upgrades from unsure matches.

    If a receipt was previously unsure-matched to a different transaction,
    remove the old match first. Same for transactions.
    """
    # Build lookup for current unsure state
    receipt_current_tx = {r["id"]: r.get("transaction_id") for r in receipts_pool}
    applied = 0

    for m in matches:
        tx_id = m["transaction_id"]
        r_id = m["receipt_id"]
        new_status = m["match_status"]

        # Check if this receipt was unsure-matched to a DIFFERENT transaction
        old_tx = receipt_current_tx.get(r_id)
        if old_tx and old_tx != tx_id:
            logger.info(f"Upgrading receipt {r_id}: removing old unsure match with tx={old_tx}")
            remove_match(old_tx)

        apply_match(tx_id, r_id, new_status, "auto")
        applied += 1

    return applied
