from datetime import datetime

from backend.core.config import settings
from backend.services.threshold_service import (
    exceeds_experimental_threshold,
    threshold_state,
)


def test_experimental_threshold_has_approved_value() -> None:
    assert settings.biometric_threshold_cosine == 0.6281865036


def test_threshold_uses_original_cosine_at_exact_boundary() -> None:
    assert exceeds_experimental_threshold(0.6281865036) is True
    assert exceeds_experimental_threshold(0.628186503599) is False


def test_threshold_states_are_prudent() -> None:
    assert threshold_state(True) == "posible_coincidencia"
    assert threshold_state(False) == "coincidencia_insuficiente"


def test_analyses_before_effective_date_remain_not_evaluated() -> None:
    historical = datetime(2026, 10, 4, 23, 13, 26)

    assert threshold_state(True, historical) == "umbral_no_evaluado"
    assert threshold_state(False, historical) == "umbral_no_evaluado"


def test_effective_date_and_later_use_persisted_decision() -> None:
    effective = datetime(2026, 10, 4, 23, 13, 27)

    assert threshold_state(True, effective) == "posible_coincidencia"
    assert threshold_state(False, effective) == "coincidencia_insuficiente"
