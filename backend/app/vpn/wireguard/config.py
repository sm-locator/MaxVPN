from dataclasses import asdict

from app.vpn.models import WireGuardClientConfig
from app.vpn.renderer import TemplateRenderer


class WireGuardConfigGenerator:
    """Generates WireGuard client configuration."""

    def __init__(self) -> None:
        self._renderer = TemplateRenderer()

    def generate(self, config: WireGuardClientConfig) -> str:
        return self._renderer.render(
            "wireguard/client.conf.j2",
            asdict(config),
        )
