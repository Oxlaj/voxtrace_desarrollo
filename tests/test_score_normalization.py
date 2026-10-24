from decimal import Decimal

from backend.services.score_normalization_service import normalize_cosine_for_persistence


def test_normalization_endpoints() -> None:
    assert normalize_cosine_for_persistence(-1) == Decimal("0.000")
    assert normalize_cosine_for_persistence(0) == Decimal("50.000")
    assert normalize_cosine_for_persistence(1) == Decimal("100.000")


def test_normalization_clamps_float_rounding() -> None:
    assert normalize_cosine_for_persistence(1.0000000000000002) == Decimal("100.000")
    assert normalize_cosine_for_persistence(-1.0000000000000002) == Decimal("0.000")


def test_normalization_preserves_order() -> None:
    assert normalize_cosine_for_persistence(-0.5) < normalize_cosine_for_persistence(0.25)
