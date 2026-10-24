import math

import pytest

from backend.services.comparison_service import ComparisonError, cosine_similarity
from backend.services.embedding_service import (
    EXPECTED_EMBEDDING_DIMENSION,
    deserialize_embedding,
    serialize_embedding,
)


def vector_with(first: float, second: float = 0.0) -> list[float]:
    values = [0.0] * EXPECTED_EMBEDDING_DIMENSION
    values[0] = first
    values[1] = second
    return values


def test_identical_vectors_have_similarity_one() -> None:
    assert cosine_similarity(vector_with(1.0), vector_with(1.0)) == pytest.approx(1.0)


def test_different_vectors_have_similarity_between_minus_one_and_one() -> None:
    result = cosine_similarity(vector_with(1.0), vector_with(-1.0, 1.0))

    assert -1.0 <= result <= 1.0
    assert result == pytest.approx(-math.sqrt(0.5))


def test_orthogonal_vectors_have_similarity_zero() -> None:
    assert cosine_similarity(vector_with(1.0), vector_with(0.0, 1.0)) == pytest.approx(0.0)


def test_dimension_is_required() -> None:
    with pytest.raises(ComparisonError, match="dimensión"):
        cosine_similarity([1.0], vector_with(1.0))


def test_non_finite_values_are_rejected() -> None:
    with pytest.raises(ComparisonError, match="no finitos"):
        cosine_similarity(vector_with(float("nan")), vector_with(1.0))
    with pytest.raises(ComparisonError, match="no finitos"):
        cosine_similarity(vector_with(float("inf")), vector_with(1.0))


def test_zero_norm_is_rejected() -> None:
    with pytest.raises(ComparisonError, match="norma cero"):
        cosine_similarity(vector_with(0.0), vector_with(1.0))


def test_similarity_is_symmetric() -> None:
    first = vector_with(2.0, 3.0)
    second = vector_with(-4.0, 1.0)

    assert cosine_similarity(first, second) == pytest.approx(cosine_similarity(second, first))


def test_serialized_embeddings_can_be_compared() -> None:
    first = vector_with(1.0, 2.0)
    second = vector_with(2.0, 1.0)

    result = cosine_similarity(
        deserialize_embedding(serialize_embedding(first)),
        deserialize_embedding(serialize_embedding(second)),
    )

    assert result == pytest.approx(0.8)
