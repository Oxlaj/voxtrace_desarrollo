from unittest.mock import MagicMock

from scripts import create_admin as create_admin_module


def test_cli_does_not_print_password_or_hash(monkeypatch, capsys) -> None:
    db = MagicMock()
    user = MagicMock(correo="admin@example.com")
    monkeypatch.setattr(
        create_admin_module,
        "create_admin",
        MagicMock(return_value=user),
    )
    monkeypatch.setattr(create_admin_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        "builtins.input",
        MagicMock(side_effect=["Admin", "admin@example.com"]),
    )
    monkeypatch.setattr(
        create_admin_module,
        "getpass",
        MagicMock(side_effect=["local-secret", "local-secret"]),
    )

    create_admin_module.main()
    output = capsys.readouterr().out

    assert "admin@example.com" in output
    assert "local-secret" not in output
    assert "password_hash" not in output
    assert "argon2" not in output.lower()
