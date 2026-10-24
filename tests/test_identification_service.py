from unittest.mock import MagicMock

import pytest

from backend.models.audio import Audio
from backend.models.embedding import Embedding
from backend.models.persona import Persona
from backend.services.comparison_service import ComparisonError
from backend.services.embedding_service import EXPECTED_EMBEDDING_DIMENSION, serialize_embedding
from backend.services.identification_service import identify_top_candidates


def vector(first: float, second: float = 0.0) -> list[float]:
    values = [0.0] * EXPECTED_EMBEDDING_DIMENSION
    values[0] = first
    values[1] = second
    return values


def person(person_id: int, identifier: str | None = None) -> Persona:
    return Persona(
        id_persona=person_id,
        identificador=identifier or f"P-{person_id}",
        nombre=f"Persona {person_id}",
        alias=f"Alias {person_id}",
    )


def audio(audio_id: int, person_id: int, reference: list[float] | None) -> Audio:
    item = Audio(id_audio=audio_id, id_persona=person_id, id_usuario=1)
    if reference is not None:
        item.embedding = Embedding(
            id_audio=audio_id,
            vector=serialize_embedding(reference),
            modelo_utilizado="test",
        )
    return item


def make_db(people: list[Persona], audios: list[Audio]) -> MagicMock:
    db = MagicMock()
    db.scalars.side_effect = [
        MagicMock(all=MagicMock(return_value=people)),
        MagicMock(all=MagicMock(return_value=audios)),
    ]
    return db


def patch_query_embedding(monkeypatch, values: list[float]) -> None:
    monkeypatch.setattr(
        "backend.services.identification_service.generate_embedding",
        lambda path: values,
    )


def test_empty_database_returns_no_candidates(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))

    assert identify_top_candidates(make_db([], []), "query.wav") == []


def test_candidates_are_ranked_by_best_then_average(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    people = [person(1), person(2), person(3)]
    audios = [
        audio(11, 1, vector(1.0)),
        audio(21, 2, vector(0.0, 1.0)),
        audio(22, 2, vector(1.0)),
        audio(31, 3, vector(-1.0)),
    ]

    results = identify_top_candidates(make_db(people, audios), "query.wav")

    assert [candidate.id_persona for candidate in results] == [1, 2, 3]
    assert [candidate.posicion for candidate in results] == [1, 2, 3]
    assert results[1].similitud_promedio == pytest.approx(0.5)


def test_top_three_limit_and_less_than_three_candidates(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    people = [person(index) for index in range(1, 6)]
    audios = [audio(index, index, vector(1.0)) for index in range(1, 6)]

    results = identify_top_candidates(make_db(people, audios), "query.wav")

    assert len(results) == 3
    assert [candidate.posicion for candidate in results] == [1, 2, 3]

    fewer = identify_top_candidates(make_db(people[:2], audios[:2]), "query.wav")
    assert len(fewer) == 2


def test_ties_use_average_then_person_id(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    people = [person(1), person(2)]
    audios = [
        audio(11, 1, vector(1.0)),
        audio(12, 1, vector(0.0, 1.0)),
        audio(21, 2, vector(1.0)),
    ]

    results = identify_top_candidates(make_db(people, audios), "query.wav")

    assert [candidate.id_persona for candidate in results] == [2, 1]
    assert results[0].similitud_promedio > results[1].similitud_promedio


def test_people_without_embeddings_are_excluded_and_missing_are_counted(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    people = [person(1), person(2), person(3)]
    audios = [
        audio(11, 1, None),
        audio(12, 1, vector(1.0)),
        audio(21, 2, None),
    ]

    results = identify_top_candidates(make_db(people, audios), "query.wav")

    assert [candidate.id_persona for candidate in results] == [1]
    assert results[0].muestras_comparadas == 1
    assert results[0].muestras_sin_embedding == 1


def test_invalid_reference_embedding_is_rejected(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))
    people = [person(1)]
    invalid = audio(11, 1, vector(1.0))
    invalid.embedding.vector = serialize_embedding(vector(0.0))

    with pytest.raises(ComparisonError, match="norma cero"):
        identify_top_candidates(make_db(people, [invalid]), "query.wav")


def test_invalid_limit_is_rejected(monkeypatch) -> None:
    patch_query_embedding(monkeypatch, vector(1.0))

    with pytest.raises(ValueError, match="límite"):
        identify_top_candidates(make_db([], []), "query.wav", limit=0)
