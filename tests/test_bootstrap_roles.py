from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.models.rol import Rol
from scripts.bootstrap_roles import BASE_ROLES, bootstrap_roles


class ScalarRows:
    def __init__(self, rows: list[Rol]) -> None:
        self.rows = rows

    def all(self) -> list[Rol]:
        return list(self.rows)


class FakeSession:
    def __init__(self, roles: list[Rol], fail_after: int | None = None) -> None:
        self.roles = roles
        self.fail_after = fail_after
        self.add_count = 0
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.users = [object()]

    def scalars(self, statement: object) -> ScalarRows:
        return ScalarRows(self.roles)

    def add(self, role: Rol) -> None:
        self.add_count += 1
        if self.fail_after == self.add_count:
            raise SQLAlchemyError("fallo controlado")
        self.roles.append(role)


def role(name: str, role_id: int, description: str | None = None) -> Rol:
    return Rol(id_rol=role_id, nombre=name, descripcion=description)


def test_bootstrap_creates_all_roles_when_database_has_none() -> None:
    db = FakeSession([])

    result = bootstrap_roles(db)

    assert result.created == tuple(BASE_ROLES)
    assert {item.nombre for item in db.roles} == set(BASE_ROLES)
    db.commit.assert_called_once_with()
    db.rollback.assert_not_called()


def test_bootstrap_preserves_existing_role_id_and_description() -> None:
    existing = role("Administrador", 41, "Descripción institucional existente")
    db = FakeSession([existing])

    result = bootstrap_roles(db)

    assert result.created == ("Investigador", "Analista")
    assert existing.id_rol == 41
    assert existing.descripcion == "Descripción institucional existente"


def test_bootstrap_with_all_roles_does_not_insert_or_duplicate() -> None:
    db = FakeSession(
        [role(name, index, description) for index, (name, description) in enumerate(BASE_ROLES.items(), 1)]
    )

    result = bootstrap_roles(db)

    assert result.created == ()
    assert db.add_count == 0
    assert len({item.nombre for item in db.roles}) == 3


def test_bootstrap_is_idempotent_when_run_repeatedly() -> None:
    db = FakeSession([])

    bootstrap_roles(db)
    bootstrap_roles(db)

    assert db.add_count == 3
    assert [item.nombre for item in db.roles].count("Administrador") == 1
    assert [item.nombre for item in db.roles].count("Investigador") == 1
    assert [item.nombre for item in db.roles].count("Analista") == 1
    assert db.commit.call_count == 2


def test_bootstrap_completes_only_empty_descriptions() -> None:
    admin = role("Administrador", 7, "   ")
    investigator = role("Investigador", 8, "Personalizada")
    analyst = role("Analista", 9, None)
    db = FakeSession([admin, investigator, analyst])

    result = bootstrap_roles(db)

    assert set(result.descriptions_completed) == {"Administrador", "Analista"}
    assert admin.descripcion == BASE_ROLES["Administrador"]
    assert investigator.descripcion == "Personalizada"
    assert analyst.descripcion == BASE_ROLES["Analista"]


def test_bootstrap_rolls_back_without_commit_on_error() -> None:
    db = FakeSession([], fail_after=2)

    with pytest.raises(SQLAlchemyError):
        bootstrap_roles(db)

    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


def test_bootstrap_does_not_modify_users() -> None:
    db = FakeSession([])
    original_users = list(db.users)

    bootstrap_roles(db)

    assert db.users == original_users
