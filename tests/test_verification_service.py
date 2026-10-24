from unittest.mock import MagicMock

import pytest

from backend.models.audio import Audio
from backend.models.embedding import Embedding
from backend.models.persona import Persona
from backend.services import verification_service
from backend.services.comparison_service import ComparisonError
from backend.services.embedding_service import EXPECTED_EMBEDDING_DIMENSION, serialize_embedding
from backend.services.verification_service import (
    NoReferenceEmbeddingsError,
    NoReferenceSamplesError,
    PersonNotFoundError,
    verify_against_person,
)


def vector(first: float, second: float = 0.0) -> list[float]:
    values = [0.0] * EXPECTED_EMBEDDING_DIMENSION
    values[0] = first
    values[1] = second
    return values


def make_audio(audio_id: int, embedding: list[float] | None) -> Audio:
    audio = Audio(id_audio=audio_id, id_persona=4, id_usuario=1)
    audio.embedding = (
        Embedding(id_audio=audio_id, vector=serialize_embedding(embedding), modelo_utilizado="test")
        if embedding is not None
        else None
    )
    return audio


def make_db(audios: list[Audio], person_exists: bool = True) -> MagicMock:
    db = MagicMock()
    db.get.return_value = Persona(id_persona=4, nombre="Persona de prueba", identificador="P-004") if person_exists else None
    db.scalars.return_value.all.return_value = audios
    return db


def patch_query_embedding(monkeypatch, values: list[float]) -> None:
    monkeypatch.setattr(verification_service, "generate_embedding", lambda path: values)


def test_person_with_one_reference(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    result = verify_against_person(make_db([make_audio(10, vector(1.0))]), 4, "query.wav")

    assert result.muestras_comparadas == 1
    assert result.similitud_mejor == pytest.approx(1.0)
    assert result.similitud_promedio == pytest.approx(1.0)


def test_person_with_multiple_references_calculates_best_and_average(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0, 0.0))
    audios = [make_audio(10, vector(1.0, 0.0)), make_audio(11, vector(0.0, 1.0))]

    result = verify_against_person(make_db(audios), 4, "query.wav")

    assert [item.id_audio for item in result.resultados_individuales] == [10, 11]
    assert result.similitud_mejor == pytest.approx(1.0)
    assert result.similitud_promedio == pytest.approx(0.5)


def test_person_not_found() -> None:
    with pytest.raises(PersonNotFoundError):
        verify_against_person(make_db([], person_exists=False), 4, "query.wav")


def test_person_without_samples(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))

    with pytest.raises(NoReferenceSamplesError):
        verify_against_person(make_db([]), 4, "query.wav")


def test_person_without_embeddings(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))

    with pytest.raises(NoReferenceEmbeddingsError):
        verify_against_person(make_db([make_audio(10, None)]), 4, "query.wav")


def test_samples_without_embedding_are_reported(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    result = verify_against_person(
        make_db([make_audio(10, None), make_audio(11, vector(1.0))]),
        4,
        "query.wav",
    )

    assert result.muestras_comparadas == 1
    assert result.muestras_sin_embedding == 1


def test_invalid_reference_embedding_is_rejected(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    invalid = make_audio(10, vector(1.0))
    invalid.embedding.vector = serialize_embedding(vector(0.0))

    with pytest.raises(ComparisonError, match="norma cero"):
        verify_against_person(make_db([invalid]), 4, "query.wav")


def test_result_preserves_mathematical_similarity(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0, 1.0))
    result = verify_against_person(
        make_db([make_audio(10, vector(1.0, 0.0))]),
        4,
        "query.wav",
    )

    assert result.resultados_individuales[0].similitud == pytest.approx(2**-0.5)
