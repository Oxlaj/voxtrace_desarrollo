from backend.database.connection import Base, SessionLocal, engine


def test_database_configuration_is_defined() -> None:
    assert engine is not None
    assert SessionLocal is not None
    assert Base.metadata.schema == "voxtrace"
