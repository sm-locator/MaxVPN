from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.client import Client
from app.models.server import Server


class BaseVPNBackend(ABC):
    """Базовый интерфейс для всех VPN-бэкендов."""

    def __init__(self, server: Server):
        self.server = server

    @abstractmethod
    def generate_keys(self) -> dict[str, str]:
        """Сгенерировать ключи клиента."""

    @abstractmethod
    def allocate_ip(self) -> str:
        """Выделить свободный IP-адрес клиенту."""

    @abstractmethod
    def generate_config(self, client: Client) -> str:
        """Сгенерировать конфигурационный файл."""

    @abstractmethod
    def generate_qr(self, client: Client) -> bytes:
        """Сгенерировать QR-код конфигурации."""

    @abstractmethod
    def add_client(self, client: Client) -> None:
        """Добавить клиента на VPN-сервер."""

    @abstractmethod
    def remove_client(self, client: Client) -> None:
        """Удалить клиента с VPN-сервера."""

    @abstractmethod
    def reload(self) -> None:
        """Перезагрузить конфигурацию VPN."""
