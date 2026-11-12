import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from jose import jwt

from app.core.config import settings


def credential_version(password_hash: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(), password_hash.encode(), hashlib.sha256
    ).hexdigest()


def create_user_access_token(user) -> str:
    return create_access_token(
        {
            "sub": user.email,
            "credential_version": credential_version(user.password_hash),
        }
    )


def create_access_token(data: dict) -> str:
    to_encode = data.copy()

    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update(
        {
            "exp": expire,
        }
    )

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
