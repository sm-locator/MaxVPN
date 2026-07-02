from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.user import UserCreate
from app.services.user import UserService


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)
@router.post("/register")
def register(
    user: UserCreate,
    db: Session = Depends(get_db),
):
    service = UserService(db)

    created_user = service.create_user(user)

    return {
        "id": created_user.id,
        "email": created_user.email,
    }