"""
Receipt ↔ Transaction Matching Engine

Scoring system:
  - Amount exact match (CAD or foreign)     +50
  - Amount within 5% (CAD or foreign)       +25
  - Merchant keyword overlap                +30
  - Date within 0 days                      +15
  - Date within 1-3 days                    +10

Thresholds:
  - score >= 65  →  matched_sure   (auto-match)
  - score >= 40  →  matched_unsure (human review)
  - score <  40  →  no match

Only receipts with processing_status='completed' are considered.
Each receipt matches at most one transaction (best score wins).
Each transaction matches at most one receipt.
"""

import logging
import re
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger("matcher")

# ── Thresholds ──
SCORE_AUTO = 65
SCORE_UNSURE = 40

# ── Scoring weights ──
AMOUNT_EXACT = 50
AMOUNT_CLOSE = 25
MERCHANT_MATCH = 30
DATE_SAME_DAY = 15
DATE_NEAR = 10

# Amount tolerance
AMOUNT_EXACT_TOL = 0.02   # within 2 cents
AMOUNT_CLOSE_PCT = 0.05   # within 5%


def _parse_date(d) -> Optional[date]:
    """Parse a date string or date object into a date."""
    if d is None:
        return None
    if isinstance(d, date):
        return d
    try:
        # Handle common formats: YYYY-MM-DD, YYYY/MM/DD
        return date.fromisoformat(str(d)[:10])
    except (ValueError, TypeError):
        return None


def _extract_keywords(text: str) -> set:
    """Extract meaningful keywords from a merchant/description string.

    Strips out short words (<3 chars) and common noise like
    transaction codes, asterisks, city names appended by Amex.
    """
    if not text:
        return set()
    # Lowercase + strip non-alphanumeric
    words = re.findall(r'[a-z]{3,}', text.lower())
    # Filter out very common noise words
    noise = {'the', 'and', 'for', 'from', 'with', 'this', 'that', 'www', 'com', 'http', 'https'}
    return set(words) - noise


def score_pair(tx: dict, receipt: dict) -> dict:
    """Score a single transaction–receipt pair.

    Returns {score, breakdown} where breakdown explains each component.
    """
    score = 0
    breakdown = []

    tx_amount = tx.get("amount_cad")
    tx_foreign = tx.get("foreign_amount")
    r_total = receipt.get("total_amount")

    # ── Amount matching ──
    if tx_amount is not None and r_total is not None:
        diff = abs(float(tx_amount) - float(r_total))
        if diff <= AMOUNT_EXACT_TOL:
            score += AMOUNT_EXACT
            breakdown.append(f"amount_exact_cad(diff={diff:.2f}) +{AMOUNT_EXACT}")
        elif float(tx_amount) != 0 and diff / abs(float(tx_amount)) <= AMOUNT_CLOSE_PCT:
            score += AMOUNT_CLOSE
            breakdown.append(f"amount_close_cad({diff:.2f}/{abs(float(tx_amount)):.2f}={diff/abs(float(tx_amount))*100:.1f}%) +{AMOUNT_CLOSE}")

    # Also check foreign amount (receipt might be in foreign currency)
    if tx_foreign is not None and r_total is not None and score < AMOUNT_EXACT:
        diff_f = abs(float(tx_foreign) - float(r_total))
        if diff_f <= AMOUNT_EXACT_TOL:
            score += AMOUNT_EXACT
            breakdown.append(f"amount_exact_foreign(diff={diff_f:.2f}) +{AMOUNT_EXACT}")
        elif float(tx_foreign) != 0 and diff_f / abs(float(tx_foreign)) <= AMOUNT_CLOSE_PCT:
            # Only add if we haven't already scored amount_close from CAD
            if score < AMOUNT_CLOSE:
                score += AMOUNT_CLOSE
                breakdown.append(f"amount_close_foreign({diff_f:.2f}/{abs(float(tx_foreign)):.2f}={diff_f/abs(float(tx_foreign))*100:.1f}%) +{AMOUNT_CLOSE}")

    # ── Merchant matching ──
    tx_keywords = _extract_keywords(tx.get("merchant", "") + " " + tx.get("description", ""))
    r_keywords = _extract_keywords(receipt.get("merchant_name", ""))
    overlap = tx_keywords & r_keywords

    if overlap:
        score += MERCHANT_MATCH
        breakdown.append(f"merchant_keywords({', '.join(sorted(overlap))}) +{MERCHANT_MATCH}")

    # ── Date proximity ──
    tx_date = _parse_date(tx.get("transaction_date"))
    r_date = _parse_date(receipt.get("receipt_date"))

    if tx_date and r_date:
        days_diff = abs((tx_date - r_date).days)
        if days_diff == 0:
            score += DATE_SAME_DAY
            breakdown.append(f"date_same_day +{DATE_SAME_DAY}")
        elif days_diff <= 3:
            score += DATE_NEAR
            breakdown.append(f"date_near({days_diff}d) +{DATE_NEAR}")

    return {"score": score, "breakdown": breakdown}


def run_matching(transactions: list, receipts: list) -> list:
    """Run matching across all transaction–receipt pairs.

    Args:
        transactions: list of dicts (from DB), only unmatched ones
        receipts: list of dicts (from DB), only completed + unmatched ones

    Returns:
        List of match results:
        [
            {
                "transaction_id": ...,
                "receipt_id": ...,
                "score": 75,
                "match_status": "matched_sure",
                "breakdown": ["amount_exact +50", "merchant_keywords(lyft) +30"],
            },
            ...
        ]
    """
    if not transactions or not receipts:
        logger.info(f"Nothing to match: {len(transactions)} transactions, {len(receipts)} receipts")
        return []

    logger.info(f"Matching {len(transactions)} transactions against {len(receipts)} receipts")

    # Score every pair
    all_scores = []
    for tx in transactions:
        for r in receipts:
            result = score_pair(tx, r)
            if result["score"] >= SCORE_UNSURE:
                all_scores.append({
                    "transaction_id": tx["id"],
                    "receipt_id": r["id"],
                    "score": result["score"],
                    "breakdown": result["breakdown"],
                })

    # Sort by score descending — best matches first
    all_scores.sort(key=lambda x: x["score"], reverse=True)

    # Greedy assignment: each transaction and receipt matched at most once
    matched_tx = set()
    matched_r = set()
    results = []

    for candidate in all_scores:
        tx_id = candidate["transaction_id"]
        r_id = candidate["receipt_id"]

        if tx_id in matched_tx or r_id in matched_r:
            continue

        score = candidate["score"]
        match_status = "matched_sure" if score >= SCORE_AUTO else "matched_unsure"

        results.append({
            "transaction_id": tx_id,
            "receipt_id": r_id,
            "score": score,
            "match_status": match_status,
            "breakdown": candidate["breakdown"],
        })

        matched_tx.add(tx_id)
        matched_r.add(r_id)

        logger.info(
            f"Match: tx={tx_id} ↔ receipt={r_id} "
            f"score={score} status={match_status} "
            f"[{', '.join(candidate['breakdown'])}]"
        )

    logger.info(
        f"Matching complete: {len(results)} matches "
        f"({sum(1 for r in results if r['match_status'] == 'matched_sure')} sure, "
        f"{sum(1 for r in results if r['match_status'] == 'matched_unsure')} unsure)"
    )

    return results
