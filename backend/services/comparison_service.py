import math

from backend.services.embedding_service import EXPECTED_EMBEDDING_DIMENSION


class ComparisonError(ValueError):
    pass


def _validate_vector(vector: list[float], name: str) -> list[float]:
    if len(vector) != EXPECTED_EMBEDDING_DIMENSION:
        raise ComparisonError(
            f"{name} debe tener dimensión {EXPECTED_EMBEDDING_DIMENSION}"
        )
    values = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in values):
        raise ComparisonError(f"{name} contiene valores no finitos")
    return values


def cosine_similarity(first: list[float], second: list[float]) -> float:
    first_values = _validate_vector(first, "El primer embedding")
    second_values = _validate_vector(second, "El segundo embedding")
    first_norm = math.sqrt(sum(value * value for value in first_values))
    second_norm = math.sqrt(sum(value * value for value in second_values))
    if first_norm == 0 or second_norm == 0:
        raise ComparisonError("No se puede comparar un vector de norma cero")
    dot_product = sum(
        first_value * second_value
        for first_value, second_value in zip(first_values, second_values)
    )
    return dot_product / (first_norm * second_norm)
