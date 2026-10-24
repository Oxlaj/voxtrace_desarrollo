from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.audio import Audio
from backend.models.persona import Persona
from backend.services.embedding_service import generate_embedding
from backend.services.verification_service import (
    IndividualVerificationResult,
    aggregate_reference_embeddings,
)


class IdentificationError(ValueError):
    pass


@dataclass(frozen=True)
class IdentificationCandidate:
    posicion: int
    id_persona: int
    identificador: str
    nombre: str
    alias: str | None
    similitud_mejor: float
    similitud_promedio: float
    muestras_comparadas: int
    muestras_sin_embedding: int
    resultados_individuales: list[IndividualVerificationResult]


def identify_top_candidates(
    db: Session,
    query_wav_path: str | Path,
    limit: int = 3,
) -> list[IdentificationCandidate]:
    if limit <= 0:
        raise IdentificationError("El límite de candidatos debe ser positivo")

    query_embedding = generate_embedding(query_wav_path)
    people = list(db.scalars(select(Persona).order_by(Persona.id_persona)).all())
    audios = list(db.scalars(select(Audio).order_by(Audio.id_persona, Audio.id_audio)).all())
    audios_by_person: dict[int, list[Audio]] = {}
    for audio in audios:
        audios_by_person.setdefault(audio.id_persona, []).append(audio)

    candidates: list[IdentificationCandidate] = []
    for person in people:
        individual_results, samples_without_embedding = aggregate_reference_embeddings(
            query_embedding,
            audios_by_person.get(person.id_persona, []),
        )
        if not individual_results:
            continue
        scores = [result.similitud for result in individual_results]
        candidates.append(
            IdentificationCandidate(
                posicion=0,
                id_persona=person.id_persona,
                identificador=person.identificador,
                nombre=person.nombre,
                alias=person.alias,
                similitud_mejor=max(scores),
                similitud_promedio=sum(scores) / len(scores),
                muestras_comparadas=len(individual_results),
                muestras_sin_embedding=samples_without_embedding,
                resultados_individuales=individual_results,
            )
        )

    ranked = sorted(
        candidates,
        key=lambda candidate: (
            -candidate.similitud_mejor,
            -candidate.similitud_promedio,
            candidate.id_persona,
        ),
    )[:limit]
    return [
        IdentificationCandidate(
            posicion=index,
            id_persona=candidate.id_persona,
            identificador=candidate.identificador,
            nombre=candidate.nombre,
            alias=candidate.alias,
            similitud_mejor=candidate.similitud_mejor,
            similitud_promedio=candidate.similitud_promedio,
            muestras_comparadas=candidate.muestras_comparadas,
            muestras_sin_embedding=candidate.muestras_sin_embedding,
            resultados_individuales=candidate.resultados_individuales,
        )
        for index, candidate in enumerate(ranked, start=1)
    ]