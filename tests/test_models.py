from backend import models
from backend.database.connection import Base


def test_all_er_tables_are_registered_in_voxtrace_schema() -> None:
    expected_tables = {
        "rol",
        "usuario",
        "persona",
        "audio",
        "embedding",
        "analisis",
        "resultado_analisis",
        "log",
    }

    assert set(Base.metadata.tables) == {
        f"voxtrace.{table_name}" for table_name in expected_tables
    }
    assert models is not None


def test_persona_name_is_required() -> None:
    persona_table = Base.metadata.tables["voxtrace.persona"]

    assert persona_table.c.nombre.nullable is False
