from ipaddress import IPv4Address

from pydantic import BaseModel, ConfigDict


class ClientCreate(BaseModel):
    client_name: str


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    ip_address: IPv4Address
    public_key: str
    config: str
