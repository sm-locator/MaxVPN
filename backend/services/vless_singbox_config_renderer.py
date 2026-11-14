from __future__ import annotations

import re
from collections.abc import Sequence
from ipaddress import IPv4Interface
from typing import Any

from backend.models.vless_config import VlessServerConfig
from backend.services.vless_singbox_renderer import VlessSingBoxRenderer


class VlessSingBoxConfigRenderer:
    """Render single-server compatibility configs and multi-server URLTest configs."""

    DEFAULT_TUN_NAME = "maxvpn0"
    DEFAULT_TUN_ADDRESS = "172.19.0.1/30"
    DEFAULT_MTU = 1380
    URLTEST_URL = "https://cp.cloudflare.com/generate_204"
    URLTEST_INTERVAL = "3m"
    URLTEST_TOLERANCE_MS = 50

    def __init__(self, outbound_renderer: VlessSingBoxRenderer | None = None) -> None:
        self._outbound_renderer = outbound_renderer or VlessSingBoxRenderer()

    def render(
        self,
        server: VlessServerConfig,
        *,
        interface_name: str = DEFAULT_TUN_NAME,
        tun_address: str = DEFAULT_TUN_ADDRESS,
        mtu: int = DEFAULT_MTU,
    ) -> dict[str, Any]:
        """Backward-compatible single-profile config used by existing tests/tools."""
        outbound = self._render_server_outbound(server, tag="vless-out")
        return self._base_config(
            [outbound, {"type": "direct", "tag": "direct"}],
            interface_name=interface_name,
            tun_address=tun_address,
            mtu=mtu,
        )

    def render_profiles(
        self,
        profiles: Sequence[tuple[int, VlessServerConfig]],
        *,
        interface_name: str = DEFAULT_TUN_NAME,
        tun_address: str = DEFAULT_TUN_ADDRESS,
        mtu: int = DEFAULT_MTU,
        interval: str = URLTEST_INTERVAL,
        tolerance_ms: int = URLTEST_TOLERANCE_MS,
    ) -> dict[str, Any]:
        """Render profile outbounds behind an automatic URLTest and manual selector."""
        if not profiles:
            raise ValueError("At least one enabled VLESS profile is required")
        if len(profiles) > 50:
            raise ValueError("At most 50 VLESS profiles can be rendered")
        if not re.fullmatch(r"[1-9][0-9]*m|[1-9][0-9]*s", interval):
            raise ValueError("URLTest interval must be specified in seconds or minutes")
        if not 0 <= tolerance_ms <= 5000:
            raise ValueError("URLTest tolerance must be between 0 and 5000 ms")

        server_outbounds: list[dict[str, Any]] = []
        tags: list[str] = []
        seen_ids: set[int] = set()
        for profile_id, server in profiles:
            if profile_id <= 0 or profile_id in seen_ids:
                raise ValueError("VLESS profile IDs must be unique positive integers")
            seen_ids.add(profile_id)
            tag = f"vless-profile-{profile_id}"
            tags.append(tag)
            server_outbounds.append(self._render_server_outbound(server, tag=tag))

        outbounds: list[dict[str, Any]] = [
            *server_outbounds,
            {
                "type": "urltest",
                "tag": "vless-auto",
                "outbounds": tags,
                "url": self.URLTEST_URL,
                "interval": interval,
                "tolerance": tolerance_ms,
                # Keep existing sessions alive during auto-selection changes.
                "interrupt_exist_connections": False,
            },
            {
                "type": "selector",
                "tag": "vless-out",
                "outbounds": ["vless-auto", *tags],
                "default": "vless-auto",
                "interrupt_exist_connections": False,
            },
            {"type": "direct", "tag": "direct"},
        ]
        config = self._base_config(
            outbounds,
            interface_name=interface_name,
            tun_address=tun_address,
            mtu=mtu,
        )
        # The API is reachable only from the router itself. MaxVPN calls it over SSH.
        config["experimental"] = {
            "clash_api": {"external_controller": "127.0.0.1:9090", "secret": ""}
        }
        return config

    def _render_server_outbound(
        self, server: VlessServerConfig, *, tag: str
    ) -> dict[str, Any]:
        outbound = self._outbound_renderer.render_outbound(server, tag=tag)
        # Resolve VLESS endpoints with the marked direct/bootstrap resolver.
        outbound["domain_resolver"] = "endpoint-dns"
        return outbound

    def _base_config(
        self,
        outbounds: list[dict[str, Any]],
        *,
        interface_name: str,
        tun_address: str,
        mtu: int,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,15}", interface_name):
            raise ValueError("TUN interface name must contain 1–15 valid characters")
        try:
            parsed_address = IPv4Interface(tun_address)
        except ValueError as exc:
            raise ValueError("TUN address must be a valid IPv4 interface") from exc
        if not 576 <= mtu <= 9000:
            raise ValueError("TUN MTU must be between 576 and 9000")

        return {
            "log": {"level": "info", "timestamp": True},
            "dns": {
                "servers": [
                    {
                        "type": "https",
                        "tag": "vless-doh",
                        "server": "1.1.1.1",
                        "server_port": 443,
                        "path": "/dns-query",
                        "tls": {"enabled": True, "server_name": "cloudflare-dns.com"},
                        "detour": "vless-out",
                    },
                    {
                        "type": "udp",
                        "tag": "endpoint-dns",
                        "server": "1.1.1.1",
                        "server_port": 53,
                        # 0x64 bypasses tunnel policy for endpoint bootstrap.
                        "routing_mark": 100,
                    },
                ],
                "final": "vless-doh",
                "strategy": "prefer_ipv4",
            },
            "inbounds": [
                {
                    "type": "tun",
                    "tag": "maxvpn-tun-in",
                    "interface_name": interface_name,
                    "address": [str(parsed_address)],
                    "mtu": mtu,
                    # LAN routes remain managed separately by MaxVPN.
                    "auto_route": False,
                }
            ],
            "outbounds": outbounds,
            "route": {
                "rules": [{"port": 53, "action": "hijack-dns"}],
                "default_domain_resolver": "endpoint-dns",
                "auto_detect_interface": True,
                "final": "vless-out",
            },
        }
