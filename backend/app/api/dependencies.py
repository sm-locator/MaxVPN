from ipaddress import IPv4Address, IPv4Network

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.dependencies import get_db
from app.exporters.config_exporter import ConfigExporter
from app.exporters.export_facade import ExportFacade
from app.exporters.qr_exporter import QRExporter
from app.infrastructure.local_command_executor import LocalCommandExecutor
from app.infrastructure.wireguard.peer_manager import SystemWireGuardPeerManager
from app.repositories.sqlalchemy.wireguard_client import (
    SQLAlchemyWireGuardClientRepository,
)
from app.vpn.ip_allocator import IPAllocator
from app.vpn.repositories import WireGuardClientRepository
from app.vpn.wireguard.config import WireGuardConfigGenerator
from app.vpn.wireguard.keys import WireGuardKeyGenerator
from app.vpn.wireguard.manager import WireGuardManager
from app.vpn.wireguard.server_settings import WireGuardServerSettings
from app.vpn.wireguard.settings import WireGuardSettings


def get_wireguard_settings() -> WireGuardSettings:
    return WireGuardSettings(
        network=IPv4Network("10.8.0.0/24"),
        reserved_addresses={
            IPv4Address("10.8.0.1"),
        },
    )


def get_wireguard_server_settings() -> WireGuardServerSettings:
    return WireGuardServerSettings(
        server_public_key=settings.WIREGUARD_SERVER_PUBLIC_KEY,
        endpoint=settings.WIREGUARD_ENDPOINT,
        dns=settings.WIREGUARD_DNS,
        allowed_ips=settings.WIREGUARD_ALLOWED_IPS,
        persistent_keepalive=settings.WIREGUARD_PERSISTENT_KEEPALIVE,
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
        peer_manager=SystemWireGuardPeerManager(
            executor=LocalCommandExecutor(),
            interface_name="wg0",
        ),
    )


def get_config_exporter() -> ConfigExporter:
    return ConfigExporter()


def get_qr_exporter() -> QRExporter:
    return QRExporter()


def get_export_facade() -> ExportFacade:
    return ExportFacade(
        config_exporter=get_config_exporter(),
        qr_exporter=get_qr_exporter(),
    )
