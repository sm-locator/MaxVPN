from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class AdminBootstrap(BaseModel):
    email: EmailStr
    password: str


class AdminCredentialsUpdate(BaseModel):
    email: EmailStr
    password: str
