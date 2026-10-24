from backend.database.connection import Base


def test_audio_has_format_and_duration_constraints() -> None:
    audio_table = Base.metadata.tables["voxtrace.audio"]
    constraint_names = {constraint.name for constraint in audio_table.constraints}

    assert "ck_audio_formato_original" in constraint_names
    assert "ck_audio_duracion_positiva" in constraint_names


def test_resultado_has_top_three_integrity_constraints() -> None:
    result_table = Base.metadata.tables["voxtrace.resultado_analisis"]
    constraint_names = {constraint.name for constraint in result_table.constraints}

    assert "uq_resultado_analisis_persona" in constraint_names
    assert "uq_resultado_analisis_posicion" in constraint_names
    assert "ck_resultado_similitud_rango" in constraint_names
