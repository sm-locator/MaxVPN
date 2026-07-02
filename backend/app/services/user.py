from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserCreate
from app.services.password import PasswordService
from app.repositories.user import UserRepository


class UserService:

    def __init__(self, db: Session):
        self.users = UserRepository(db)

    def create_user(self, user_data: UserCreate) -> User:
        
        existing_user = self.users.get_by_email(user_data.email)

        if existing_user:
           raise ValueError("User already exists")
        
        hashed_password = PasswordService.hash_password(
           user_data.password
        )

        user = User(
           email=user_data.email,
           password_hash=hashed_password,
        )

        return self.users.create(user)