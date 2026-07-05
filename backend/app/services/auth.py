from datetime import datetime, timedelta, UTC

from jose import jwt

SECRET_KEY = "CHANGE_ME_IN_ENV"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


class AuthService:

    @staticmethod
    def create_access_token(user_id: int) -> str:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": str(user_id),
            "exp": expire,
        }

        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)