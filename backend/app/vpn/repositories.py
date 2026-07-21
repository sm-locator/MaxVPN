from __future__ import annotations

from ipaddress import IPv4Address
from typing import Protocol

from app.vpn.models import WireGuardClient


class WireGuardClientRepository(Protocol):
    def get_used_addresses(self) -> set[IPv4Address]: ...

    def add(
        self,
        client: WireGuardClient,
    ) -> None: ...
