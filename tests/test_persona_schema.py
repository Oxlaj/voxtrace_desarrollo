from backend.schemas.persona import PersonaCreate, PersonaUpdate


def test_persona_create_requires_name_and_identifier() -> None:
    persona = PersonaCreate(nombre="Caso 001", identificador="P-001")

    assert persona.nombre == "Caso 001"
    assert persona.identificador == "P-001"


def test_persona_update_accepts_partial_changes() -> None:
    update = PersonaUpdate(alias="Voz de referencia")

    assert update.model_dump(exclude_unset=True) == {"alias": "Voz de referencia"}
