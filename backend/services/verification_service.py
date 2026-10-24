from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.audio import Audio
from backend.models.persona import Persona
from backend.services.comparison_service import cosine_similarity
from backend.services.embedding_service import deserialize_embedding, generate_embedding


class VerificationError(ValueError):
    pass


class PersonNotFoundError(VerificationError):
    pass


class NoReferenceSamplesError(VerificationError):
    pass


class NoReferenceEmbeddingsError(VerificationError):
    pass


@dataclass(frozen=True)
class IndividualVerificationResult:
    id_audio: int
    similitud: float


@dataclass(frozen=True)
class VerificationResult:
    id_persona: int
    muestras_comparadas: int
    muestras_sin_embedding: int
    resultados_individuales: list[IndividualVerificationResult]
    similitud_mejor: float
    similitud_promedio: float


def aggregate_reference_embeddings(
    query_embedding: list[float],
    audios: list[Audio],
) -> tuple[list[IndividualVerificationResult], int]:
    results: list[IndividualVerificationResult] = []
    samples_without_embedding = 0
    for audio in audios:
        if audio.embedding is None:
            samples_without_embedding += 1
            continue
        reference_embedding = deserialize_embedding(audio.embedding.vector)
        results.append(
            IndividualVerificationResult(
                id_audio=audio.id_audio,
                similitud=cosine_similarity(query_embedding, reference_embedding),
            )
        )
    return results, samples_without_embedding


def verify_against_person(
    db: Session,
    persona_id: int,
    query_wav_path: str | Path,
) -> VerificationResult:
    if db.get(Persona, persona_id) is None:
        raise PersonNotFoundError("La persona no existe")

    query_embedding = generate_embedding(query_wav_path)
    audios = list(
        db.scalars(
            select(Audio)
            .where(Audio.id_persona == persona_id)
            .order_by(Audio.id_audio)
        ).all()
    )
    if not audios:
        raise NoReferenceSamplesError("La persona no tiene muestras de referencia")

    results, samples_without_embedding = aggregate_reference_embeddings(
        query_embedding,
        audios,
    )

    if not results:
        raise NoReferenceEmbeddingsError(
            "La persona no tiene embeddings de referencia disponibles"
        )

    scores = [result.similitud for result in results]
    return VerificationResult(
        id_persona=persona_id,
        muestras_comparadas=len(results),
        muestras_sin_embedding=samples_without_embedding,
        resultados_individuales=results,
        similitud_mejor=max(scores),
        similitud_promedio=sum(scores) / len(scores),
    )
