from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from poise.core.config import get_settings

_settings = get_settings()

# bcrypt 强制 72 字节密码上限：超出部分截断（仍能正常验证）。
_BCRYPT_MAX = 72


def _to_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    return encoded[:_BCRYPT_MAX]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(password), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    subject: str,
    role: str,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=expires_minutes or _settings.api_jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _settings.api_secret_key, algorithm=_settings.api_jwt_alg)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            _settings.api_secret_key,
            algorithms=[_settings.api_jwt_alg],
        )
    except JWTError as e:
        raise ValueError(f"invalid token: {e}") from e
