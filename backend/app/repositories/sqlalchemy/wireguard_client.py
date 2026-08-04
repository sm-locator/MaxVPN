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
            private_key=client.private_key,
            public_key=client.public_key,
            ip_address=str(client.ip_address),
        )

        self._session.add(orm_client)

    def get_by_name(
        self,
        name: str,
    ) -> WireGuardClient | None:
        orm_client = self._session.scalar(
            select(ORMWireGuardClient).where(
                ORMWireGuardClient.name == name,
            )
        )

        if orm_client is None:
            return None

        return WireGuardClient(
            name=orm_client.name,
            private_key=orm_client.private_key,
            public_key=orm_client.public_key,
            ip_address=IPv4Address(orm_client.ip_address),
        )

    def delete(
        self,
        client: WireGuardClient,
    ) -> None:
        orm_client = self._session.scalar(
            select(ORMWireGuardClient).where(
                ORMWireGuardClient.name == client.name,
            )
        )

        if orm_client is not None:
            self._session.delete(orm_client)

    def update(
        self,
        client_name: str,
        client: WireGuardClient,
    ) -> None:
        orm_client = self._session.scalar(
            select(ORMWireGuardClient).where(
                ORMWireGuardClient.name == client_name,
            )
        )

        if orm_client is None:
            return

        orm_client.name = client.name
        orm_client.description = client.description
        orm_client.enabled = client.enabled
