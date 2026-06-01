from poise.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_roundtrip():
    h = hash_password("Poise@2026")
    assert verify_password("Poise@2026", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    token = create_access_token(subject="u1", role="admin", extra={"entity_id": "e1"})
    payload = decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["role"] == "admin"
    assert payload["entity_id"] == "e1"
