from ipaddress import IPv4Address, IPv4Network

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.repositories.sqlalchemy.wireguard_client import (
    SQLAlchemyWireGuardClientRepository,
)
from app.vpn.ip_allocator import IPAllocator
from app.vpn.repositories import WireGuardClientRepository
from app.vpn.wireguard.config import WireGuardConfigGenerator
from app.vpn.wireguard.keys import WireGuardKeyGenerator
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.settings import WireGuardSettings


def get_wireguard_settings() -> WireGuardSettings:
    return WireGuardSettings(
        network=IPv4Network("10.8.0.0/24"),
        reserved_addresses={
            IPv4Address("10.8.0.1"),
        },
    )


def get_wireguard_repository(
    db: Session = Depends(get_db),
) -> WireGuardClientRepository:
    return SQLAlchemyWireGuardClientRepository(db)


def get_wireguard_manager(
    settings: WireGuardSettings = Depends(get_wireguard_settings),
    repository: WireGuardClientRepository = Depends(get_wireguard_repository),
) -> WireGuardManager:
    return WireGuardManager(
        settings=settings,
        repository=repository,
        allocator=IPAllocator(),
        key_generator=WireGuardKeyGenerator(),
        config_generator=WireGuardConfigGenerator(),
    )
