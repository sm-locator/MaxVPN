from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.security import create_access_token
from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.auth import Token
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


@router.post(
    "/login",
    response_model=Token,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    service = UserService(db)

    user = service.authenticate(
        form_data.username,
        form_data.password,
    )

    access_token = create_access_token(
        {
            "sub": user.email,
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

    access_token = create_access_token(
        {
            "sub": user.email,
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.get("/me")
def me(
    current_user: User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
    }
