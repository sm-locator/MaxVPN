from ipaddress import IPv4Address

from app.database.models.wireguard_client import (
    WireGuardClient as ORMWireGuardClient,
)
from app.vpn.models import WireGuardClient
from sqlalchemy import select
from sqlalchemy.orm import Session


class SQLAlchemyWireGuardClientRepository:
    def __init__(self, session: Session):
        self._session = session

    def get_used_addresses(self) -> set[IPv4Address]:
        clients = self._session.scalars(select(ORMWireGuardClient)).all()

        return {IPv4Address(client.ip_address) for client in clients}

    def add(self, client: WireGuardClient) -> None:
        orm_client = ORMWireGuardClient(
            name=client.name,
            public_key=client.public_key,
            ip_address=str(client.ip_address),
        )

        self._session.add(orm_client)
