from fastapi import HTTPException, status

from app.models.roles import UserRole
from app.models.user import User


class AuthService:
    @staticmethod
    def require_role(
        user: User,
        role: UserRole,
    ) -> User:
        if user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    @staticmethod
    def require_admin(user: User) -> User:
        return AuthService.require_role(
            user,
            UserRole.ADMIN,
        )
