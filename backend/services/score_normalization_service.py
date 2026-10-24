from decimal import Decimal, ROUND_HALF_UP


def normalize_cosine_for_persistence(cosine: float) -> Decimal:
    """Map cosine [-1, 1] to a technical score in [0, 100]."""
    bounded = min(1.0, max(-1.0, float(cosine)))
    normalized = ((bounded + 1.0) / 2.0) * 100.0
    return Decimal(str(normalized)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
