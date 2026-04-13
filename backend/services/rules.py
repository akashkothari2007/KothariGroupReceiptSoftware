"""
Rules engine for auto-filling transaction fields.

apply_rules(transaction_id)
  - Vendor mappings: merchant keyword match → gl_code_id
  - City-company rules: city (+province) match → company_id
  - Only overwrites NULL fields — never clobbers manual edits

apply_rules_batch(transaction_ids)
  - Runs apply_rules for a list of transaction IDs (used after statement upload)
"""

import logging
from sqlalchemy import text
from db import engine

logger = logging.getLogger("rules")


def _load_vendor_mappings(conn) -> list[dict]:
    rows = conn.execute(
        text("SELECT vendor_name, gl_code_id FROM vendor_mappings")
    ).fetchall()
    return [{"vendor_name": r[0].strip().lower(), "gl_code_id": str(r[1])} for r in rows if r[0] and r[1]]


def _load_city_company_rules(conn) -> list[dict]:
    rows = conn.execute(
        text("SELECT city, province, company_id FROM city_company_rules")
    ).fetchall()
    return [
        {
            "city": r[0].strip().lower() if r[0] else None,
            "province": r[1].strip().upper() if r[1] else None,
            "company_id": str(r[2]),
        }
        for r in rows if r[0] and r[2]
    ]


def _match_vendor(merchant: str, description: str, mappings: list[dict]) -> str | None:
    """Find the best vendor mapping for a merchant/description.
    Uses case-insensitive substring match on vendor_name.
    Also checks with spaces removed so 'air canada' matches 'AIRCANADA'."""
    if not merchant and not description:
        return None
    combined = ((merchant or "") + " " + (description or "")).lower()
    combined_nospace = combined.replace(" ", "")
    for m in mappings:
        vendor = m["vendor_name"]
        if vendor in combined or vendor.replace(" ", "") in combined_nospace:
            return m["gl_code_id"]
    return None


def _match_city(city: str, province: str, rules: list[dict]) -> str | None:
    """Find the best city-company rule. Prefers city+province match over city-only."""
    if not city:
        return None
    city_lower = city.strip().lower()
    province_upper = province.strip().upper() if province else None

    # First pass: try exact city+province match
    for r in rules:
        if r["city"] == city_lower and r["province"] and province_upper and r["province"] == province_upper:
            return r["company_id"]

    # Second pass: city-only rules (where province is NULL)
    for r in rules:
        if r["city"] == city_lower and not r["province"]:
            return r["company_id"]

    return None


def apply_rules(transaction_id: str):
    """Apply vendor and city rules to a single transaction.
    Only fills in NULL gl_code_id and company_id."""
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT merchant, description, city, province, gl_code_id, company_id
                FROM transactions WHERE id = :tid
            """),
            {"tid": transaction_id},
        ).fetchone()

        if not row:
            return

        merchant, description, city, province, current_gl, current_company = row
        updates = {}
        params = {"tid": transaction_id}

        if current_gl is None:
            vendor_mappings = _load_vendor_mappings(conn)
            gl = _match_vendor(merchant, description, vendor_mappings)
            if gl:
                updates["gl_code_id"] = ":gl_code_id"
                params["gl_code_id"] = gl
                logger.info(f"Rule: tx={transaction_id} vendor match → gl_code_id={gl}")

        if current_company is None:
            city_rules = _load_city_company_rules(conn)
            company = _match_city(city, province, city_rules)
            if company:
                updates["company_id"] = ":company_id"
                params["company_id"] = company
                logger.info(f"Rule: tx={transaction_id} city match ({city}, {province}) → company_id={company}")

        if updates:
            set_clause = ", ".join(f"{k} = {v}" for k, v in updates.items())
            conn.execute(
                text(f"UPDATE transactions SET {set_clause} WHERE id = :tid"),
                params,
            )


def apply_rules_batch(transaction_ids: list[str]):
    """Apply rules to a batch of transactions. Loads mappings once."""
    if not transaction_ids:
        return

    with engine.begin() as conn:
        vendor_mappings = _load_vendor_mappings(conn)
        city_rules = _load_city_company_rules(conn)

        for tid in transaction_ids:
            row = conn.execute(
                text("""
                    SELECT merchant, description, city, province, gl_code_id, company_id
                    FROM transactions WHERE id = :tid
                """),
                {"tid": tid},
            ).fetchone()

            if not row:
                continue

            merchant, description, city, province, current_gl, current_company = row
            updates = {}
            params = {"tid": tid}

            if current_gl is None:
                gl = _match_vendor(merchant, description, vendor_mappings)
                if gl:
                    updates["gl_code_id"] = ":gl_code_id"
                    params["gl_code_id"] = gl
                    logger.info(f"Rule: tx={tid} vendor match → gl_code_id={gl}")

            if current_company is None:
                company = _match_city(city, province, city_rules)
                if company:
                    updates["company_id"] = ":company_id"
                    params["company_id"] = company
                    logger.info(f"Rule: tx={tid} city match ({city}, {province}) → company_id={company}")

            if updates:
                set_clause = ", ".join(f"{k} = {v}" for k, v in updates.items())
                conn.execute(
                    text(f"UPDATE transactions SET {set_clause} WHERE id = :tid"),
                    params,
                )

    logger.info(f"Rules applied to {len(transaction_ids)} transactions")
