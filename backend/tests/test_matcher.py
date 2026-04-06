"""
Permanent tests for the matching engine.
Run with: python -m pytest tests/ -v  (from backend/)
Or just: python tests/test_matcher.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import pytest
except ImportError:
    pytest = None
from services.matcher import score_pair, run_matching, _extract_keywords, _parse_date, SCORE_AUTO
from datetime import date


# ── Fixtures ──

def make_tx(**overrides):
    base = {
        "id": "tx-1", "transaction_date": "2026-03-13",
        "merchant": "LYFT   *RIDE WED 7AM", "description": "VANCOUVER",
        "amount_cad": 25.50, "foreign_amount": None, "foreign_currency": None,
        "match_status": "unmatched", "matched_receipt_id": None,
    }
    base.update(overrides)
    return base


def make_receipt(**overrides):
    base = {
        "id": "r-1", "merchant_name": "Lyft Ride", "receipt_date": "2026-03-13",
        "total_amount": 25.50, "tax_amount": 3.32, "tax_type": "GST",
        "country": "CA", "match_status": "unmatched", "transaction_id": None,
    }
    base.update(overrides)
    return base


# ── Helpers ──

class TestParseDate:
    def test_iso_string(self):
        assert _parse_date("2026-03-13") == date(2026, 3, 13)

    def test_datetime_string(self):
        assert _parse_date("2026-03-13T00:00:00") == date(2026, 3, 13)

    def test_date_object(self):
        assert _parse_date(date(2026, 3, 13)) == date(2026, 3, 13)

    def test_none(self):
        assert _parse_date(None) is None

    def test_garbage(self):
        assert _parse_date("garbage") is None


class TestExtractKeywords:
    def test_amex_merchant(self):
        kw = _extract_keywords("LYFT   *RIDE WED 7AM    VANCOUVER")
        assert "lyft" in kw
        assert "ride" in kw
        assert "vancouver" in kw

    def test_digits_filtered(self):
        kw = _extract_keywords("LYFT *RIDE 7AM")
        assert "7am" not in kw

    def test_domain_style(self):
        assert "amazon" in _extract_keywords("AMAZON.CA")

    def test_empty(self):
        assert _extract_keywords("") == set()
        assert _extract_keywords(None) == set()


# ── Country-aware scoring ──

class TestCountryAwareScoring:
    def test_canadian_receipt_cad_match(self):
        """CA receipt + CAD amount = full points."""
        result = score_pair(make_tx(), make_receipt())
        # exact cad(50) + merchant(30) + same day(15) = 95
        assert result["score"] == 95

    def test_foreign_receipt_foreign_amount(self):
        """US receipt + foreign amount match = full points."""
        tx = make_tx(amount_cad=83.75, foreign_amount=60.00, foreign_currency="USD",
                     merchant="ADOBE INC", description="SAN JOSE")
        r = make_receipt(merchant_name="Adobe", total_amount=60.00, country="US",
                         receipt_date="2026-03-11")
        result = score_pair(tx, r)
        # foreign exact(50) + merchant(30) + date near(10) = 90
        assert result["score"] == 90

    def test_foreign_receipt_cad_no_foreign_amount(self):
        """US receipt + CAD tx with NO foreign_amount = skip cross-currency penalty.
        AI country detection is unreliable; trust the transaction data."""
        tx = make_tx(amount_cad=300.00, merchant="RANDOM STORE", description="TORONTO",
                     transaction_date="2026-03-13")
        r = make_receipt(merchant_name="Something Else", total_amount=300.00,
                         country="US", receipt_date="2026-03-13")
        result = score_pair(tx, r)
        # No foreign_amount on tx → skip cross-currency → full CAD exact(50) + date(15) = 65
        assert result["score"] == 65

    def test_foreign_receipt_cad_WITH_foreign_amount(self):
        """US receipt + CAD match but tx HAS foreign_amount = cross-currency (15)."""
        tx = make_tx(amount_cad=300.00, foreign_amount=215.00, foreign_currency="USD",
                     merchant="RANDOM STORE", description="TORONTO",
                     transaction_date="2026-03-13")
        r = make_receipt(merchant_name="Something Else", total_amount=300.00,
                         country="US", receipt_date="2026-03-13")
        result = score_pair(tx, r)
        # tx HAS foreign_amount → cross-currency penalty applies → 15 + date(15) = 30
        assert result["score"] == 30

    def test_canadian_receipt_foreign_cross_currency(self):
        """CA receipt matching foreign amount = downgraded to 15."""
        tx = make_tx(amount_cad=83.75, foreign_amount=25.50, merchant="RANDOM",
                     transaction_date="2026-03-13")
        r = make_receipt(merchant_name="Something", total_amount=25.50,
                         country="CA", receipt_date="2026-03-13")
        result = score_pair(tx, r)
        # Foreign amount matches CA receipt → cross-currency(15) + date(15) = 30
        assert result["score"] == 30

    def test_no_country_defaults_canadian(self):
        """Empty country treated as Canadian."""
        tx = make_tx(amount_cad=50.00)
        r = make_receipt(total_amount=50.00, country="")
        result = score_pair(tx, r)
        assert result["score"] == 95  # full CAD match


# ── The Expedia bug regression ──

class TestExpediaBug:
    """Regression test for the $300 cross-currency false positive."""

    def test_wrong_match_below_threshold(self):
        """CDN FDN has no foreign_amount, so cross-currency penalty is skipped.
        But no merchant overlap + 22 days apart → still below auto threshold."""
        wrong_tx = make_tx(id="wrong", merchant="CDN FDN PHY DISABLED 00",
                           description="TORONTO", amount_cad=300.00,
                           transaction_date="2026-02-18")
        receipt = make_receipt(id="exp", merchant_name="Expedia", total_amount=300.00,
                              country="US", receipt_date="2026-03-12")
        result = score_pair(wrong_tx, receipt)
        # CAD exact(50) + no merchant(0) + 22 days(−10) = 40 → unsure, not auto
        assert result["score"] < SCORE_AUTO, "Wrong match should not auto-match"

    def test_right_match_auto(self):
        right_tx = make_tx(id="right", merchant="EXPEDIA INC", description="BELLEVUE",
                           amount_cad=418.76, foreign_amount=300.00, foreign_currency="USD",
                           transaction_date="2026-03-13")
        receipt = make_receipt(id="exp", merchant_name="Expedia", total_amount=300.00,
                              country="US", receipt_date="2026-03-12")
        result = score_pair(right_tx, receipt)
        assert result["score"] >= 65, "Correct foreign match should auto-match"

    def test_greedy_picks_correct(self):
        wrong_tx = make_tx(id="cdn-fdn", merchant="CDN FDN PHY DISABLED 00",
                           description="TORONTO", amount_cad=300.00,
                           transaction_date="2026-02-18")
        right_tx = make_tx(id="expedia-tx", merchant="EXPEDIA INC",
                           description="BELLEVUE", amount_cad=418.76,
                           foreign_amount=300.00, foreign_currency="USD",
                           transaction_date="2026-03-13")
        receipt = make_receipt(id="exp-r", merchant_name="Expedia",
                              total_amount=300.00, country="US",
                              receipt_date="2026-03-12")
        results = run_matching([wrong_tx, right_tx], [receipt])
        assert len(results) == 1
        assert results[0]["transaction_id"] == "expedia-tx"
        assert results[0]["match_status"] == "matched_sure"


# ── General scoring ──

class TestScoring:
    def test_amount_only(self):
        tx = make_tx(merchant="RANDOM", description="PLACE")
        r = make_receipt(merchant_name="Different", receipt_date="2026-03-20", country="CA")
        result = score_pair(tx, r)
        # exact CAD(50) + no merchant + 7 days(0) = 50
        assert result["score"] == 50

    def test_close_amount(self):
        tx = make_tx(amount_cad=100.00, merchant="STORE ABC", description="VANCOUVER")
        r = make_receipt(merchant_name="Store", total_amount=103.00,
                         receipt_date="2026-03-13", country="CA")
        result = score_pair(tx, r)
        # close cad(25) + merchant "store"(30) + same day(15) = 70
        assert result["score"] == 70

    def test_no_match(self):
        tx = make_tx(amount_cad=999.99, merchant="AAA", description="BBB")
        r = make_receipt(total_amount=1.00, merchant_name="CCC", receipt_date="2025-01-01")
        assert score_pair(tx, r)["score"] == 0

    def test_date_near(self):
        tx = make_tx(amount_cad=100.00, merchant="AAA")
        r = make_receipt(total_amount=100.00, merchant_name="BBB",
                         receipt_date="2026-03-15", country="CA")
        result = score_pair(tx, r)
        # exact cad(50) + date near 2d(10) = 60
        assert result["score"] == 60

    def test_amex_garbled_merchant(self):
        tx = make_tx(merchant="UBER   *EATS  PENDING", description="VANCOUVER BC",
                     amount_cad=42.00)
        r = make_receipt(total_amount=42.00, merchant_name="Uber Eats",
                         receipt_date="2026-03-13", country="CA")
        result = score_pair(tx, r)
        assert result["score"] == 95

    def test_negative_amount(self):
        tx = make_tx(amount_cad=-50.00)
        r = make_receipt(total_amount=-50.00)
        assert score_pair(tx, r)["score"] == 95


# ── run_matching ──

class TestRunMatching:
    def test_greedy_1_to_1(self):
        txs = [make_tx(id="tx-1", amount_cad=25.50),
               make_tx(id="tx-2", amount_cad=42.00, merchant="UBER EATS")]
        receipts = [make_receipt(id="r-1", total_amount=25.50),
                    make_receipt(id="r-2", total_amount=42.00, merchant_name="Uber Eats")]
        results = run_matching(txs, receipts)
        assert len(results) == 2
        assert {r["transaction_id"] for r in results} == {"tx-1", "tx-2"}

    def test_no_double_assignment(self):
        txs = [make_tx(id="tx-1", amount_cad=25.50),
               make_tx(id="tx-2", amount_cad=25.50, merchant="DIFFERENT", description="TORONTO")]
        receipts = [make_receipt(id="r-1", total_amount=25.50)]
        results = run_matching(txs, receipts)
        assert len(results) == 1
        assert results[0]["transaction_id"] == "tx-1"  # better merchant match

    def test_empty_inputs(self):
        assert run_matching([], []) == []
        assert run_matching([make_tx()], []) == []
        assert run_matching([], [make_receipt()]) == []

    def test_unsure_threshold(self):
        tx = make_tx(amount_cad=100.00, merchant="STARBUCKS COFFEE")
        r = make_receipt(total_amount=104.00, merchant_name="Starbucks",
                         receipt_date="2026-04-01", country="CA")
        results = run_matching([tx], [r])
        assert len(results) == 1
        assert results[0]["match_status"] == "matched_unsure"


# ── Compound keywords ──

class TestCompoundKeywords:
    def test_namecheap_hyphenated_vs_joined(self):
        """NAME-CHEAP.COM should match 'namecheap'."""
        tx_kw = _extract_keywords("NAME-CHEAP.COM*HOSTING")
        r_kw = _extract_keywords("Namecheap")
        assert tx_kw & r_kw, f"No overlap: {tx_kw} vs {r_kw}"

    def test_aircanada_single_vs_split(self):
        """AIRCANADA (one word) should match 'Air Canada' (two words)."""
        tx_kw = _extract_keywords("AIRCANADA")
        r_kw = _extract_keywords("Air Canada")
        assert tx_kw & r_kw, f"No overlap: {tx_kw} vs {r_kw}"

    def test_uber_eats_still_works(self):
        """Normal multi-word merchants still match."""
        tx_kw = _extract_keywords("UBER   *EATS  PENDING")
        r_kw = _extract_keywords("Uber Eats")
        assert "uber" in (tx_kw & r_kw)
        assert "eats" in (tx_kw & r_kw)

    def test_namecheap_full_score(self):
        """Namecheap tx + receipt should get merchant points."""
        tx = make_tx(amount_cad=83.75, foreign_amount=14.58, foreign_currency="USD",
                     merchant="NAME-CHEAP.COM*HOSTING", description="PHOENIX",
                     transaction_date="2026-03-11")
        r = make_receipt(merchant_name="Namecheap", total_amount=14.58,
                         country="US", receipt_date="2026-03-11")
        result = score_pair(tx, r)
        # foreign exact(50) + merchant(30) + same day(15) = 95
        assert result["score"] == 95

    def test_aircanada_full_score(self):
        """AIRCANADA tx + Air Canada receipt should get merchant points."""
        tx = make_tx(amount_cad=322.93, merchant="AIRCANADA", description="WINNIPEG",
                     transaction_date="2026-03-23")
        r = make_receipt(merchant_name="Air Canada", total_amount=322.93,
                         country="CA", receipt_date="2026-03-23")
        result = score_pair(tx, r)
        # exact CAD(50) + merchant(30) + same day(15) = 95
        assert result["score"] == 95


# ── Date limits ──

class TestDateLimits:
    def test_over_30_days_disqualified(self):
        """Matches >30 days apart should score 0."""
        tx = make_tx(amount_cad=44.10, merchant="UBER", transaction_date="2026-03-22")
        r = make_receipt(total_amount=44.10, merchant_name="Uber",
                         receipt_date="2026-04-25", country="CA")
        result = score_pair(tx, r)
        assert result["score"] == 0

    def test_15_days_gets_penalty(self):
        """Matches 15 days apart get -10 penalty."""
        tx = make_tx(amount_cad=100.00, merchant="STORE", transaction_date="2026-03-01")
        r = make_receipt(total_amount=100.00, merchant_name="Store",
                         receipt_date="2026-03-16", country="CA")
        result = score_pair(tx, r)
        # exact CAD(50) + merchant(30) + date_far(-10) = 70
        assert result["score"] == 70

    def test_7_days_no_bonus_no_penalty(self):
        """4-7 days apart: no date bonus, no penalty."""
        tx = make_tx(amount_cad=100.00, merchant="AAA", transaction_date="2026-03-13")
        r = make_receipt(total_amount=100.00, merchant_name="BBB",
                         receipt_date="2026-03-19", country="CA")
        result = score_pair(tx, r)
        # exact CAD(50) only — no date bonus, no penalty
        assert result["score"] == 50

    def test_westjet_57_days_disqualified(self):
        """Regression: WestJet tx 57 days from receipt should NOT match."""
        tx = make_tx(amount_cad=500.00, merchant="WESTJET", transaction_date="2026-03-30")
        r = make_receipt(total_amount=500.00, merchant_name="WestJet",
                         receipt_date="2026-05-26", country="CA")
        result = score_pair(tx, r)
        assert result["score"] == 0


# ── Null amount guard ──

class TestNullAmountGuard:
    def test_null_total_skipped(self):
        """Receipt with null total should score 0."""
        tx = make_tx(amount_cad=322.93, merchant="AIRCANADA")
        r = make_receipt(total_amount=None, merchant_name="Air Canada")
        result = score_pair(tx, r)
        assert result["score"] == 0

    def test_zero_total_skipped(self):
        """Receipt with 0.00 total should score 0."""
        tx = make_tx(amount_cad=322.93, merchant="AIRCANADA")
        r = make_receipt(total_amount=0.00, merchant_name="Air Canada")
        result = score_pair(tx, r)
        assert result["score"] == 0


# ── Minimum score guard ──

class TestMinimumScoreGuard:
    def test_no_amount_no_merchant_is_zero(self):
        """No amount match + no merchant match = score 0 (not just low)."""
        tx = make_tx(amount_cad=999.99, merchant="AAA", description="BBB",
                     transaction_date="2026-03-13")
        r = make_receipt(total_amount=1.00, merchant_name="CCC",
                         receipt_date="2026-03-13", country="CA")
        result = score_pair(tx, r)
        assert result["score"] == 0


# ── Grays Cafe regression ──

class TestGraysCafe:
    def test_cad_tx_with_ai_wrong_country(self):
        """Grays Cafe: AI says US but tx has no foreign_amount → skip penalty."""
        tx = make_tx(amount_cad=38.37, merchant="GRAYS CAFE", description="SIDNEY",
                     transaction_date="2026-03-18")
        r = make_receipt(merchant_name="Grays Cafe", total_amount=38.37,
                         country="US", receipt_date="2026-03-18")
        result = score_pair(tx, r)
        # No foreign_amount → skip cross-currency → exact CAD(50) + merchant(30) + date(15) = 95
        assert result["score"] == 95
        assert result["score"] >= SCORE_AUTO


# ── Run directly ──

if __name__ == "__main__":
    if pytest:
        pytest.main([__file__, "-v"])
    else:
        # Run without pytest
        passed = 0
        failed = 0
        for name, cls in list(globals().items()):
            if isinstance(cls, type) and name.startswith("Test"):
                inst = cls()
                for method_name in sorted(dir(inst)):
                    if method_name.startswith("test_"):
                        try:
                            getattr(inst, method_name)()
                            print(f"  PASS: {name}.{method_name}")
                            passed += 1
                        except AssertionError as e:
                            print(f"  FAIL: {name}.{method_name} — {e}")
                            failed += 1
        print(f"\n{'All' if not failed else failed} {'passed' if not failed else 'failed'}: {passed} passed, {failed} failed")
