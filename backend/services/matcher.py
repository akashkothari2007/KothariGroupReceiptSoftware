"""
Receipt ↔ Transaction Matching Engine

Scoring system:
  Amount (country-aware):
  - Correct currency match exact             +50
  - Correct currency match within 5%         +25
  - Cross-currency coincidental exact        +15  (downgraded — suspicious)
  Other signals:
  - Merchant keyword overlap                 +30
  - Date within 0 days                       +15
  - Date within 1-3 days                     +10

Country logic:
  - Receipt country != CA → "foreign" receipt → prefer foreign_amount
  - Receipt country == CA or unknown → prefer amount_cad
  - BUT if transaction has NO foreign_amount, skip cross-currency penalty
    (AI country detection is unreliable; tx currency data is authoritative)

Date limits:
  - >7 days apart: no date bonus
  - >14 days apart: -10 penalty
  - >30 days apart: disqualified (score = 0)

Guards:
  - Receipt with null/zero total_amount: skip (no auto-match)
  - Must score >0 on at least amount OR merchant (no garbage matches)

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
AMOUNT_CROSS_CURRENCY = 15   # coincidental match in wrong currency
MERCHANT_MATCH = 30
DATE_SAME_DAY = 15
DATE_NEAR = 10
DATE_FAR_PENALTY = -10       # >14 days apart

# Amount tolerance
AMOUNT_EXACT_TOL = 0.02   # within 2 cents
AMOUNT_CLOSE_PCT = 0.05   # within 5%

# Date limits
DATE_MAX_DAYS = 30           # beyond this, disqualify entirely


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

    Handles compound words in both directions:
    - "NAME-CHEAP.COM" → {name, cheap, namecheap, com}
    - "namecheap" (6+ chars) → {namecheap} (checked against other side's parts)
    - "AIRCANADA" → {aircanada, air, canada} (split long words into known parts)

    Strips out short words (<3 chars) and common noise.
    """
    if not text:
        return set()
    lowered = text.lower()

    # Step 1: split on any non-alpha characters to get raw parts
    raw_parts = re.findall(r'[a-z]+', lowered)

    # Step 2: also join adjacent parts to form compound keywords
    # e.g. ["name", "cheap", "com"] also generates "namecheap", "cheapcom"
    compounds = set()
    for i in range(len(raw_parts) - 1):
        joined = raw_parts[i] + raw_parts[i + 1]
        if len(joined) >= 4:
            compounds.add(joined)

    # Step 3: for long single words (6+ chars), try splitting into 2 parts
    # so "aircanada" → "air" + "canada", "namecheap" → "name" + "cheap"
    splits = set()
    for word in raw_parts:
        if len(word) >= 6:
            for split_pos in range(3, len(word) - 2):
                left = word[:split_pos]
                right = word[split_pos:]
                if len(left) >= 3 and len(right) >= 3:
                    splits.add(left)
                    splits.add(right)

    # Step 4: filter to 3+ chars, remove noise
    noise = {'the', 'and', 'for', 'from', 'with', 'this', 'that', 'www', 'com', 'http', 'https'}
    keywords = set(w for w in raw_parts if len(w) >= 3) - noise
    keywords |= compounds - noise
    keywords |= splits - noise

    return keywords


def score_pair(tx: dict, receipt: dict) -> dict:
    """Score a single transaction–receipt pair.

    Returns {score, breakdown} where breakdown explains each component.
    """
    score = 0
    breakdown = []

    tx_amount = tx.get("amount_cad")
    tx_foreign = tx.get("foreign_amount")
    r_total = receipt.get("total_amount")
    r_country = (receipt.get("country") or "").strip().upper()
    is_foreign_receipt = r_country != "" and r_country != "CA"

    # Guard: skip receipts with null/zero total — no amount to score on
    if r_total is None or float(r_total) == 0:
        return {"score": 0, "breakdown": ["skip: receipt has no amount"]}

    # ── Country-aware amount matching ──
    # Key insight: if the transaction has NO foreign_amount, the AI's country
    # detection is unreliable. A CAD-only transaction matching a receipt amount
    # should be treated as a normal CAD match regardless of receipt country.
    # Only apply cross-currency penalty when the tx actually HAS a foreign amount
    # (proving it's a real foreign transaction).
    tx_has_foreign = tx_foreign is not None and float(tx_foreign) != 0
    use_cross_currency = is_foreign_receipt and tx_has_foreign

    cad_score = 0
    cad_label = None
    foreign_score = 0
    foreign_label = None

    if tx_amount is not None and r_total is not None:
        diff = abs(float(tx_amount) - float(r_total))
        if diff <= AMOUNT_EXACT_TOL:
            if use_cross_currency:
                cad_score = AMOUNT_CROSS_CURRENCY
                cad_label = f"amount_cad_cross_currency(diff={diff:.2f}) +{AMOUNT_CROSS_CURRENCY}"
            else:
                cad_score = AMOUNT_EXACT
                cad_label = f"amount_exact_cad(diff={diff:.2f}) +{AMOUNT_EXACT}"
        elif float(tx_amount) != 0 and diff / abs(float(tx_amount)) <= AMOUNT_CLOSE_PCT:
            if not use_cross_currency:
                cad_score = AMOUNT_CLOSE
                cad_label = f"amount_close_cad({diff:.2f}/{abs(float(tx_amount)):.2f}={diff/abs(float(tx_amount))*100:.1f}%) +{AMOUNT_CLOSE}"

    if tx_foreign is not None and r_total is not None:
        diff_f = abs(float(tx_foreign) - float(r_total))
        if diff_f <= AMOUNT_EXACT_TOL:
            if is_foreign_receipt:
                foreign_score = AMOUNT_EXACT
                foreign_label = f"amount_exact_foreign(diff={diff_f:.2f}) +{AMOUNT_EXACT}"
            else:
                foreign_score = AMOUNT_CROSS_CURRENCY
                foreign_label = f"amount_foreign_cross_currency(diff={diff_f:.2f}) +{AMOUNT_CROSS_CURRENCY}"
        elif float(tx_foreign) != 0 and diff_f / abs(float(tx_foreign)) <= AMOUNT_CLOSE_PCT:
            if is_foreign_receipt:
                foreign_score = AMOUNT_CLOSE
                foreign_label = f"amount_close_foreign({diff_f:.2f}/{abs(float(tx_foreign)):.2f}={diff_f/abs(float(tx_foreign))*100:.1f}%) +{AMOUNT_CLOSE}"

    # Take the best amount score
    amount_pts = 0
    if foreign_score >= cad_score and foreign_score > 0:
        amount_pts = foreign_score
        score += foreign_score
        breakdown.append(foreign_label)
    elif cad_score > 0:
        amount_pts = cad_score
        score += cad_score
        breakdown.append(cad_label)

    # ── Merchant matching ──
    tx_keywords = _extract_keywords(tx.get("merchant", "") + " " + tx.get("description", ""))
    r_keywords = _extract_keywords(receipt.get("merchant_name", ""))
    overlap = tx_keywords & r_keywords

    merchant_pts = 0
    if overlap:
        merchant_pts = MERCHANT_MATCH
        score += MERCHANT_MATCH
        breakdown.append(f"merchant_keywords({', '.join(sorted(overlap))}) +{MERCHANT_MATCH}")

    # Guard: must have at least amount OR merchant match — prevents garbage
    if amount_pts == 0 and merchant_pts == 0:
        return {"score": 0, "breakdown": ["skip: no amount or merchant match"]}

    # ── Date proximity ──
    tx_date = _parse_date(tx.get("transaction_date"))
    r_date = _parse_date(receipt.get("receipt_date"))

    if tx_date and r_date:
        days_diff = abs((tx_date - r_date).days)

        # Hard cutoff: >30 days = disqualify entirely
        if days_diff > DATE_MAX_DAYS:
            return {"score": 0, "breakdown": [f"disqualified: {days_diff} days apart (>{DATE_MAX_DAYS}d limit)"]}

        if days_diff == 0:
            score += DATE_SAME_DAY
            breakdown.append(f"date_same_day +{DATE_SAME_DAY}")
        elif days_diff <= 3:
            score += DATE_NEAR
            breakdown.append(f"date_near({days_diff}d) +{DATE_NEAR}")
        elif days_diff > 14:
            score += DATE_FAR_PENALTY
            breakdown.append(f"date_far({days_diff}d) {DATE_FAR_PENALTY}")

    return {"score": max(score, 0), "breakdown": breakdown}


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
