from __future__ import annotations

from backend.models.client_config import ClientConfig
from backend.ports.config_renderer import ConfigRenderer


class WireGuardConfigRenderer(ConfigRenderer):
    """
    Renders a WireGuard client configuration.
    """

    def render(self, config: ClientConfig) -> str:
        return f"""[Interface]
PrivateKey = {config.key_pair.private_key}
Address = {config.tunnel.address}
DNS = {config.tunnel.dns}
MTU = {config.tunnel.mtu}

[Peer]
PublicKey = {config.peer.public_key}
Endpoint = {config.server.endpoint}
AllowedIPs = {config.peer.allowed_ips}
PersistentKeepalive = {config.peer.persistent_keepalive}
"""
