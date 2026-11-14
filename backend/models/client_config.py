from __future__ import annotations

from dataclasses import dataclass

from backend.models.key_pair import KeyPair
from backend.models.peer import Peer
from backend.models.server import Server
from backend.models.tunnel import Tunnel


@dataclass(slots=True)
class ClientConfig:
    """
    Complete VPN client configuration.
    """

    server: Server

    key_pair: KeyPair

    tunnel: Tunnel

    peer: Peer
