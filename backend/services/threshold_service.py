from datetime import datetime
from typing import Literal

from backend.core.config import settings

ThresholdState = Literal[
    "umbral_no_evaluado",
    "posible_coincidencia",
    "coincidencia_insuficiente",
]


def exceeds_experimental_threshold(cosine_similarity: float) -> bool:
    """Decide sobre el coseno original, antes de normalizarlo o redondearlo."""
    return cosine_similarity >= settings.biometric_threshold_cosine


def threshold_state(
    exceeds_threshold: bool,
    analysis_date: datetime | None = None,
) -> ThresholdState:
    if (
        analysis_date is not None
        and analysis_date < settings.biometric_threshold_effective_at
    ):
        return "umbral_no_evaluado"
    return "posible_coincidencia" if exceeds_threshold else "coincidencia_insuficiente"
