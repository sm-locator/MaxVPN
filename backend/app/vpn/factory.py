from app.models.enums import VPNProtocol
from app.models.server import Server
from app.vpn.amneziawg.backend import AmneziaWGBackend
from app.vpn.base import BaseVPNBackend
from app.vpn.wireguard.backend import WireGuardBackend


class VPNBackendFactory:
    """Factory for creating VPN backend instances."""

    @staticmethod
    def create(server: Server) -> BaseVPNBackend:
        if server.vpn_protocol == VPNProtocol.WIREGUARD:
            return WireGuardBackend(server)

        if server.vpn_protocol == VPNProtocol.AMNEZIAWG:
            return AmneziaWGBackend(server)

        raise ValueError(f"Unsupported VPN protocol: {server.vpn_protocol}")
