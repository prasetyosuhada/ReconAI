from app.agents.orchestrator import (
    route_after_bookkeeping,
    route_after_extraction,
    route_after_reconciliation,
)


def test_route_after_extraction_success():
    next_step = route_after_extraction(
        {
            "status": "completed",
            "confidence_score": 0.95,
            "needs_review": False,
            "vendor_name": "Toko Gramedia",
            "total_amount": 100000.0,
        }
    )
    assert next_step == "proceed_to_bookkeeping"


def test_route_after_extraction_low_confidence():
    next_step = route_after_extraction(
        {
            "status": "needs_review",
            "confidence_score": 0.80,  # < 0.85 threshold
            "needs_review": True,
            "vendor_name": "Toko Gramedia",
            "total_amount": 100000.0,
        }
    )
    assert next_step == "extraction_review_required"


def test_route_after_extraction_missing_fields():
    next_step = route_after_extraction(
        {
            "status": "completed",
            "confidence_score": 0.90,
            "needs_review": False,
            "vendor_name": None,  # Missing vendor
            "total_amount": 100000.0,
        }
    )
    assert next_step == "extraction_review_required"


def test_route_after_bookkeeping_success():
    next_step = route_after_bookkeeping(
        {
            "status": "completed",
            "confidence_score": 0.92,
            "uses_sensitive_account": False,
            "is_balanced": True,
            "needs_review": False,
            "risk_flags": [],
        }
    )
    assert next_step == "ready_to_post"


def test_route_after_bookkeeping_sensitive_account():
    next_step = route_after_bookkeeping(
        {
            "status": "needs_review",
            "confidence_score": 0.95,
            "uses_sensitive_account": True,  # Sensitive account trigger
            "is_balanced": True,
            "needs_review": True,
            "risk_flags": ["uses_sensitive_account"],
        }
    )
    assert next_step == "bookkeeping_review_required"


def test_route_after_bookkeeping_unbalanced():
    next_step = route_after_bookkeeping(
        {
            "status": "needs_review",
            "confidence_score": 0.90,
            "uses_sensitive_account": False,
            "is_balanced": False,  # Unbalanced entry trigger
            "needs_review": True,
            "risk_flags": ["unbalanced_entry"],
        }
    )
    assert next_step == "bookkeeping_review_required"


def test_route_after_reconciliation_success():
    next_step = route_after_reconciliation(
        {
            "status": "completed",
            "confidence_score": 0.95,
            "needs_review": False,
            "recommended_status": "matched",
        }
    )
    assert next_step == "matched"


def test_route_after_reconciliation_review_required():
    next_step = route_after_reconciliation(
        {
            "status": "needs_review",
            "confidence_score": 0.80,
            "needs_review": True,
            "recommended_status": "possible_match_review_required",
        }
    )
    assert next_step == "reconciliation_review_required"
