from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.server import ServerStatus


class ServerCreate(BaseModel):
    name: str
    country: str
    city: str
    hostname: str
    public_ip: str
    wireguard_port: int
    enabled: bool = True
    display_order: int = 0


class ServerUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    city: str | None = None
    hostname: str | None = None
    public_ip: str | None = None
    wireguard_port: int | None = None
    status: ServerStatus | None = None
    enabled: bool | None = None
    display_order: int | None = None


class ServerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str
    city: str
    hostname: str
    public_ip: str
    wireguard_port: int
    status: ServerStatus
    enabled: bool
    display_order: int
    created_at: datetime
    updated_at: datetime
