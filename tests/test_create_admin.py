from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.core.security import verify_password
from backend.models.rol import Rol
from scripts.create_admin import create_admin


class FakeUser:
    correo = "admin@example.com"


def test_create_admin_hashes_password_without_returning_plaintext() -> None:
    db = MagicMock()
    role = Rol(id_rol=7, nombre="Administrador")
    db.scalar.side_effect = [None, role]
    db.refresh.side_effect = lambda user: None

    user = create_admin(db, " Admin ", "ADMIN@example.com", "local-secret")

    assert user.correo == "admin@example.com"
    assert user.password_hash != "local-secret"
    assert verify_password("local-secret", user.password_hash)
    assert user.nombre == "Admin"
    assert db.commit.called
    db.rollback.assert_not_called()


def test_create_admin_rolls_back_database_error() -> None:
    db = MagicMock()
    db.scalar.side_effect = [None, None]
    db.flush.side_effect = SQLAlchemyError("database failure")

    with pytest.raises(SQLAlchemyError):
        create_admin(db, "Admin", "admin@example.com", "local-secret")

    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()
