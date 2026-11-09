from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.security import create_access_token
from app.database.dependencies import get_db
from app.models.user import User
from app.schemas.auth import Token
from app.schemas.user import (
    AdminBootstrap,
    AdminCredentialsUpdate,
    UserCreate,
)
from app.services.user import UserService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.get("/bootstrap/status")
def bootstrap_status(
    db: Session = Depends(get_db),
):
    service = UserService(db)

    return {
        "available": service.admin_bootstrap_available(),
    }


@router.post("/bootstrap")
def bootstrap_admin(
    data: AdminBootstrap,
    db: Session = Depends(get_db),
):
    service = UserService(db)

    try:
        admin = service.create_admin(
            email=str(data.email),
            password=data.password,
        )
    except ValueError as exc:
        if str(exc) == "Admin already exists":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="admin_already_exists",
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    access_token = create_access_token(
        {
            "sub": admin.email,
        }
    )

    return {
        "id": admin.id,
        "email": admin.email,
        "access_token": access_token,
        "token_type": "bearer",
    }


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

    try:
        user = service.authenticate(
            form_data.username,
            form_data.password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

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


@router.put("/me/credentials")
def update_my_credentials(
    data: AdminCredentialsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if str(current_user.role) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_required",
        )

    service = UserService(db)

    try:
        user = service.update_credentials(
            user=current_user,
            email=str(data.email),
            password=data.password,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    access_token = create_access_token(
        {
            "sub": user.email,
        }
    )

    return {
        "id": user.id,
        "email": user.email,
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
