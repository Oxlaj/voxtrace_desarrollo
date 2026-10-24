import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from sqlalchemy import select

from backend.database.connection import SessionLocal
from backend.models.audio import Audio
from backend.services.audio_processing_service import process_audio_copy
from backend.services.identification_service import IdentificationCandidate, identify_top_candidates
from backend.services.score_normalization_service import normalize_cosine_for_persistence


@dataclass(frozen=True)
class QueryResult:
    test_id: str
    condition: str
    true_person_id: int | None
    experimental_speaker_id: str | None
    query_id: str
    top_candidates: list[dict]
    correct_position: int | None
    top1_hit: bool | None
    top3_hit: bool | None


QUERY_FIELDS = ["test_id", "condition", "true_person_id", "experimental_speaker_id", "query_id", "correct_position", "top1_hit", "top3_hit"] + [
    f"top{position}_{field}" for position in range(1, 4) for field in ("person_id", "score_cosine", "score_normalized")
]
SCORE_FIELDS = ["test_id", "condition", "query_id", "true_person_id", "experimental_speaker_id", "candidate_person_id", "reference_id", "score_type", "score_cosine", "score_normalized"]


def evaluate_query(test_id: str, true_person_id: int | None, query_id: str, candidates: list[IdentificationCandidate], reference_ids: dict[int, str] | None = None, condition: str = "KNOWN", experimental_speaker_id: str | None = None) -> tuple[QueryResult, list[dict]]:
    top = candidates[:3]
    is_known = condition == "KNOWN"
    position = next((item.posicion for item in candidates if item.id_persona == true_person_id), None) if is_known else None
    result = QueryResult(test_id, condition, true_person_id, experimental_speaker_id, query_id, [
        {"position": c.posicion, "person_id": c.id_persona, "score_cosine": c.similitud_mejor,
         "score_normalized": float(normalize_cosine_for_persistence(c.similitud_mejor))} for c in top
    ], position, position == 1 if is_known else None, position is not None and position <= 3 if is_known else None)
    scores = [{"test_id": test_id, "condition": condition, "query_id": query_id, "true_person_id": true_person_id,
               "experimental_speaker_id": experimental_speaker_id,
               "candidate_person_id": c.id_persona, "reference_id": (reference_ids or {}).get(r.id_audio, str(r.id_audio)),
               "score_type": "unknown_impostor" if not is_known else "genuine" if c.id_persona == true_person_id else "known_impostor",
               "score_cosine": r.similitud,
               "score_normalized": float(normalize_cosine_for_persistence(r.similitud))}
              for c in candidates for r in c.resultados_individuales]
    return result, scores


def summarize(results: list[QueryResult]) -> dict:
    known = [result for result in results if result.condition == "KNOWN"]
    unknown = [result for result in results if result.condition == "UNKNOWN"]
    top1 = sum(result.top1_hit is True for result in known)
    top3 = sum(result.top3_hit is True for result in known)
    positions = [result.correct_position for result in known if result.correct_position is not None]
    unknown_top1 = [result.top_candidates[0]["score_cosine"] for result in unknown if result.top_candidates]
    return {
        "known": {
            "total_queries": len(known), "top1_hits": top1, "top3_hits": top3,
            "not_in_top3": len(known) - top3,
            "top1_accuracy": top1 / len(known) if known else 0.0,
            "top3_accuracy": top3 / len(known) if known else 0.0,
            "average_correct_position_when_present": mean(positions) if positions else None,
        },
        "unknown": {
            "total_queries": len(unknown),
            "experimental_speakers": len({result.experimental_speaker_id for result in unknown}),
            "top1_score_cosine": {
                "count": len(unknown_top1),
                "minimum": min(unknown_top1) if unknown_top1 else None,
                "maximum": max(unknown_top1) if unknown_top1 else None,
                "average": mean(unknown_top1) if unknown_top1 else None,
            },
        },
        "threshold_evaluated": False,
    }


def validate_manifest(data: dict) -> None:
    references = data.get("references", []); queries = data.get("queries", [])
    if not queries:
        raise ValueError("El manifiesto no contiene consultas")
    reference_ids = [str(item.get("dataset_audio_id", "")).strip() for item in references]
    query_ids = [str(item.get("dataset_audio_id", "")).strip() for item in queries]
    test_ids = [str(item.get("test_id", "")).strip() for item in queries]
    if not all(reference_ids) or len(reference_ids) != len(set(reference_ids)):
        raise ValueError("dataset_audio_id debe ser obligatorio y único entre referencias")
    if not all(query_ids) or len(query_ids) != len(set(query_ids)):
        raise ValueError("dataset_audio_id debe ser obligatorio y único entre consultas")
    if set(reference_ids).intersection(query_ids):
        raise ValueError("Referencias y consultas deben usar audios distintos")
    if not all(test_ids) or len(test_ids) != len(set(test_ids)):
        raise ValueError("test_id debe ser obligatorio y único")
    for item in queries:
        condition = item.get("condition")
        if condition not in {"KNOWN", "UNKNOWN"}:
            raise ValueError("condition debe ser KNOWN o UNKNOWN")
        if not str(item.get("path", "")).strip():
            raise ValueError("Cada consulta debe incluir una ruta relativa")
        if condition == "KNOWN":
            if item.get("person_id") is None:
                raise ValueError("Las consultas KNOWN requieren person_id")
            if item.get("experimental_speaker_id") is not None:
                raise ValueError("Las consultas KNOWN no utilizan experimental_speaker_id")
        else:
            if item.get("person_id") is not None:
                raise ValueError("Las consultas UNKNOWN no pueden utilizar person_id")
            if not str(item.get("experimental_speaker_id", "")).strip():
                raise ValueError("Las consultas UNKNOWN requieren experimental_speaker_id")


def ensure_query_is_independent(source: Path, reference_hashes: set[str], previous_query_hashes: set[str] | None = None) -> str:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest in reference_hashes:
        raise ValueError("Un audio de consulta coincide con una referencia registrada")
    if previous_query_hashes is not None and digest in previous_query_hashes:
        raise ValueError("Dos consultas son binariamente idénticas; existe contaminación experimental")
    return digest


def export_results(output: Path, results: list[QueryResult], scores: list[dict]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    query_rows = []
    for result in results:
        row = {"test_id": result.test_id, "condition": result.condition, "true_person_id": result.true_person_id,
               "experimental_speaker_id": result.experimental_speaker_id, "query_id": result.query_id,
               "correct_position": result.correct_position, "top1_hit": result.top1_hit, "top3_hit": result.top3_hit}
        for index in range(3):
            candidate = result.top_candidates[index] if index < len(result.top_candidates) else {}
            for key in ("person_id", "score_cosine", "score_normalized"): row[f"top{index + 1}_{key}"] = candidate.get(key)
        query_rows.append(row)
    for name, rows, fields in (("queries.csv", query_rows, QUERY_FIELDS), ("scores.csv", scores, SCORE_FIELDS)):
        with (output / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    (output / "summary.json").write_text(json.dumps(summarize(results), indent=2), encoding="utf-8")


def run(manifest_path: Path, output: Path) -> None:
    data = json.loads(manifest_path.read_text(encoding="utf-8")); validate_manifest(data)
    db = SessionLocal(); results = []; scores = []
    try:
        eligible = list(db.scalars(select(Audio).where(Audio.embedding.has()).order_by(Audio.id_audio)).all())
        declared = {int(item["audio_id"]) for item in data.get("references", [])}
        if declared != {item.id_audio for item in eligible}: raise ValueError("El manifiesto debe declarar todas las referencias elegibles de la base")
        references = {int(item["audio_id"]): str(item["dataset_audio_id"]) for item in data["references"]}
        reference_hashes = {item.hash_archivo.lower() for item in eligible}
        if any(int(item["person_id"]) != next(audio.id_persona for audio in eligible if audio.id_audio == int(item["audio_id"])) for item in data["references"]):
            raise ValueError("La persona declarada no corresponde a la referencia registrada")
        eligible_people = {audio.id_persona for audio in eligible}
        query_hashes: set[str] = set()
        for item in data["queries"]:
            condition = item["condition"]
            true_person_id = int(item["person_id"]) if condition == "KNOWN" else None
            if condition == "KNOWN" and true_person_id not in eligible_people:
                raise ValueError("La persona real de la consulta no tiene referencias elegibles")
            source = (manifest_path.parent / item["path"]).resolve()
            digest = ensure_query_is_independent(source, reference_hashes, query_hashes)
            query_hashes.add(digest)
            processed = process_audio_copy(source, "consultas")
            try:
                candidates = identify_top_candidates(db, processed.processed_path, limit=max(3, len(eligible_people)))
                result, query_scores = evaluate_query(
                    str(item["test_id"]), true_person_id, str(item["dataset_audio_id"]),
                    candidates, references, condition,
                    str(item["experimental_speaker_id"]) if condition == "UNKNOWN" else None,
                )
                results.append(result); scores.extend(query_scores)
            finally: processed.processed_path.unlink(missing_ok=True)
        export_results(output, results, scores)
    finally: db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluación experimental 1:N sin umbral")
    parser.add_argument("manifest", type=Path); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); run(args.manifest, args.output)
