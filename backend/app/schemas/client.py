from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ClientBase(BaseModel):
    name: str = Field(max_length=100)
    server_id: int

    address: str = Field(max_length=32)
    dns: str = Field(max_length=255)

    allowed_ips: str = Field(
        default="0.0.0.0/0",
        max_length=255,
    )

    persistent_keepalive: int = 25

    enabled: bool = True


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    server_id: int | None = None

    address: str | None = Field(default=None, max_length=32)
    dns: str | None = Field(default=None, max_length=255)

    allowed_ips: str | None = Field(
        default=None,
        max_length=255,
    )

    persistent_keepalive: int | None = None

    enabled: bool | None = None


class ClientRead(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    public_key: str
    preshared_key: str | None

    created_at: datetime
    updated_at: datetime
