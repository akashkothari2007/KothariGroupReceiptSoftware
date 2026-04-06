"""
Fetch unmatched transactions + receipts, run the matcher, write results.

run_matching_for_statement(statement_id)
  - Fetches unmatched transactions for that statement
  - Fetches all completed + unmatched receipts
  - Runs the scoring engine
  - Writes each match to DB

run_matching_for_receipt(receipt_id)
  - Fetches the receipt's date, finds which statements overlap
  - Fetches unmatched transactions from those statements
  - Runs the scoring engine against just this receipt
  - Writes match to DB if found
"""

import logging
from sqlalchemy import text
from db import engine
from services.matcher import run_matching
from services.match_writer import apply_match

logger = logging.getLogger("match_run")


def _fetch_unmatched_transactions(conn, statement_id: str) -> list:
    rows = conn.execute(
        text("""
            SELECT id, transaction_date, merchant, description,
                   amount_cad, foreign_amount, foreign_currency, match_status
            FROM transactions
            WHERE statement_id = :sid
              AND (matched_receipt_id IS NULL)
        """),
        {"sid": statement_id},
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "transaction_date": r[1].isoformat() if r[1] else None,
            "merchant": r[2],
            "description": r[3],
            "amount_cad": float(r[4]) if r[4] is not None else None,
            "foreign_amount": float(r[5]) if r[5] is not None else None,
            "foreign_currency": r[6],
            "match_status": r[7],
        }
        for r in rows
    ]


def _fetch_unmatched_receipts(conn) -> list:
    rows = conn.execute(
        text("""
            SELECT id, merchant_name, receipt_date, total_amount,
                   tax_amount, tax_type, country, match_status
            FROM receipts
            WHERE processing_status = 'completed'
              AND (transaction_id IS NULL)
        """)
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "merchant_name": r[1],
            "receipt_date": r[2].isoformat() if r[2] else None,
            "total_amount": float(r[3]) if r[3] is not None else None,
            "tax_amount": float(r[4]) if r[4] is not None else None,
            "tax_type": r[5],
            "country": r[6],
            "match_status": r[7],
        }
        for r in rows
    ]


def run_matching_for_statement(statement_id: str) -> list:
    """Run matching for all unmatched transactions in a statement."""
    logger.info(f"Running matching for statement {statement_id}")

    with engine.connect() as conn:
        transactions = _fetch_unmatched_transactions(conn, statement_id)
        receipts = _fetch_unmatched_receipts(conn)

    logger.info(f"Found {len(transactions)} unmatched transactions, {len(receipts)} unmatched receipts")

    matches = run_matching(transactions, receipts)

    for m in matches:
        apply_match(m["transaction_id"], m["receipt_id"], m["match_status"], "auto")

    logger.info(f"Statement {statement_id}: {len(matches)} matches applied")
    return matches


def run_matching_for_receipt(receipt_id: str) -> list:
    """Run matching for a single newly-completed receipt against all statements."""
    logger.info(f"Running matching for receipt {receipt_id}")

    with engine.connect() as conn:
        # Fetch this receipt
        row = conn.execute(
            text("""
                SELECT id, merchant_name, receipt_date, total_amount,
                       tax_amount, tax_type, country, match_status, transaction_id
                FROM receipts
                WHERE id = :rid AND processing_status = 'completed'
            """),
            {"rid": receipt_id},
        ).fetchone()

        if not row:
            logger.info(f"Receipt {receipt_id} not found or not completed, skipping")
            return []

        if row[8] is not None:
            logger.info(f"Receipt {receipt_id} already matched, skipping")
            return []

        receipt = {
            "id": str(row[0]),
            "merchant_name": row[1],
            "receipt_date": row[2].isoformat() if row[2] else None,
            "total_amount": float(row[3]) if row[3] is not None else None,
            "tax_amount": float(row[4]) if row[4] is not None else None,
            "tax_type": row[5],
            "country": row[6],
            "match_status": row[7],
        }

        # Fetch unmatched transactions from all statements
        tx_rows = conn.execute(
            text("""
                SELECT id, transaction_date, merchant, description,
                       amount_cad, foreign_amount, foreign_currency, match_status
                FROM transactions
                WHERE matched_receipt_id IS NULL
            """)
        ).fetchall()

        transactions = [
            {
                "id": str(r[0]),
                "transaction_date": r[1].isoformat() if r[1] else None,
                "merchant": r[2],
                "description": r[3],
                "amount_cad": float(r[4]) if r[4] is not None else None,
                "foreign_amount": float(r[5]) if r[5] is not None else None,
                "foreign_currency": r[6],
                "match_status": r[7],
            }
            for r in tx_rows
        ]

    logger.info(f"Matching receipt against {len(transactions)} unmatched transactions")

    matches = run_matching(transactions, [receipt])

    for m in matches:
        apply_match(m["transaction_id"], m["receipt_id"], m["match_status"], "auto")

    logger.info(f"Receipt {receipt_id}: {len(matches)} matches applied")
    return matches
