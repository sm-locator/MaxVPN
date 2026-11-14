from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Client:
    """
    VPN client registered on a VPN server.
    """

    id: int | None
    name: str
    server_id: int
    private_key: str
    public_key: str
    address: str

    description: str | None = None
    enabled: bool = True
