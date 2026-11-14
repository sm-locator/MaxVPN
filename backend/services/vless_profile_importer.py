from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from backend.models.vless_config import (
    VlessRealityConfig,
    VlessServerConfig,
)
from backend.services.vless_config_parser import VlessConfigParser


class VlessProfileImporter:
    """
    Import VLESS links and HAPP/Xray-style JSON profiles.

    Initial URI support is intentionally limited to TCP and
    REALITY or no TLS. Unsupported security modes are rejected
    rather than silently converted to a different transport.
    """

    def __init__(
        self,
        json_parser: VlessConfigParser | None = None,
    ) -> None:
        self._json_parser = json_parser or VlessConfigParser()

    def parse(
        self,
        source: str | Mapping[str, Any],
    ) -> VlessServerConfig:
        if isinstance(source, str):
            stripped = source.strip()

            if stripped.lower().startswith("vless://"):
                return self._parse_uri(stripped)

        return self._json_parser.parse(source)

    def _parse_uri(self, source: str) -> VlessServerConfig:
        try:
            parsed = urlsplit(source)
            address = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid VLESS URL host or port") from exc

        if parsed.scheme.lower() != "vless":
            raise ValueError("VLESS URL must use the vless:// scheme")

        uuid = unquote(parsed.username or "").strip()

        if not address:
            raise ValueError("VLESS URL must contain a server address")

        if not uuid:
            raise ValueError("VLESS URL must contain a user UUID")

        if port is None or not 1 <= port <= 65535:
            raise ValueError("VLESS URL must contain a valid server port")

        query = parse_qs(parsed.query, keep_blank_values=True)

        def get_value(name: str, default: str | None = None) -> str | None:
            values = query.get(name)

            if not values:
                return default

            value = values[0].strip()
            return value if value else default

        encryption = (get_value("encryption", "none") or "none").lower()

        if encryption != "none":
            raise ValueError(f"Unsupported VLESS encryption setting: {encryption!r}")

        network = (get_value("type", "tcp") or "tcp").lower()

        if network != "tcp":
            raise ValueError(f"Unsupported VLESS network: {network!r}; TCP is required")

        flow = get_value("flow")

        if flow not in (None, "xtls-rprx-vision"):
            raise ValueError(f"Unsupported VLESS flow: {flow!r}")

        security = (get_value("security", "none") or "none").lower()
        reality = None

        if security == "reality":
            public_key = get_value("pbk")
            server_name = get_value("sni")

            if not public_key:
                raise ValueError("REALITY VLESS URL must contain the pbk parameter")

            if not server_name:
                raise ValueError("REALITY VLESS URL must contain the sni parameter")

            # An empty short ID is valid for some REALITY profiles.
            short_id = query.get("sid", [""])[0].strip()

            reality = VlessRealityConfig(
                public_key=public_key,
                server_name=server_name,
                short_id=short_id,
                fingerprint=get_value("fp"),
            )
        elif security not in ("none", ""):
            raise ValueError(f"Unsupported VLESS security mode: {security!r}")

        name = unquote(parsed.fragment).strip() or f"{address}:{port}"

        return VlessServerConfig(
            name=name,
            address=address,
            port=port,
            uuid=uuid,
            flow=flow,
            network=network,
            reality=reality,
        )
