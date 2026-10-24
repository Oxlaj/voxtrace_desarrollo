from backend.core.security import hash_password, verify_password


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "Correct-Horse-42!"
    hashed_password = hash_password(password)

    assert hashed_password != password
    assert verify_password(password, hashed_password)
    assert not verify_password("wrong-password", hashed_password)
