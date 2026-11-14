from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=1024)


class AdminBootstrap(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=1024)


class AdminCredentialsUpdate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=1024)
