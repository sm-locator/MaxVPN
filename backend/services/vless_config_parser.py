from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from backend.models.vless_config import (
    VlessRealityConfig,
    VlessServerConfig,
)


class VlessConfigParser:
    """Parse HAPP/Xray-style JSON into a MaxVPN VLESS server model."""

    def parse(self, source: str | Mapping[str, Any]) -> VlessServerConfig:
        document = self._load(source)
        outbound = self._find_vless_outbound(document)

        settings = self._mapping(outbound.get("settings"), "outbound.settings")
        vnext = settings.get("vnext")
        if not isinstance(vnext, list) or not vnext:
            raise ValueError("VLESS outbound must contain non-empty settings.vnext")

        server_entry = self._mapping(vnext[0], "outbound.settings.vnext[0]")
        address = self._required_string(
            server_entry.get("address"),
            "outbound.settings.vnext[0].address",
        )
        port = self._required_port(
            server_entry.get("port"),
            "outbound.settings.vnext[0].port",
        )

        users = server_entry.get("users")
        if not isinstance(users, list) or not users:
            raise ValueError(
                "VLESS outbound must contain non-empty settings.vnext[0].users"
            )

        user = self._mapping(
            users[0],
            "outbound.settings.vnext[0].users[0]",
        )
        uuid = self._required_string(
            user.get("id"),
            "outbound.settings.vnext[0].users[0].id",
        )
        flow = self._optional_string(
            user.get("flow"),
            "outbound.settings.vnext[0].users[0].flow",
        )

        stream = self._mapping(
            outbound.get("streamSettings"),
            "outbound.streamSettings",
        )
        network = (
            self._optional_string(
                stream.get("network"),
                "outbound.streamSettings.network",
            )
            or "tcp"
        )
        security = self._optional_string(
            stream.get("security"),
            "outbound.streamSettings.security",
        )

        reality = None
        if security == "reality":
            reality_map = self._mapping(
                stream.get("realitySettings"),
                "outbound.streamSettings.realitySettings",
            )
            reality = VlessRealityConfig(
                public_key=self._required_string(
                    reality_map.get("publicKey"),
                    "outbound.streamSettings.realitySettings.publicKey",
                ),
                server_name=self._required_string(
                    reality_map.get("serverName"),
                    "outbound.streamSettings.realitySettings.serverName",
                ),
                short_id=self._required_string(
                    reality_map.get("shortId"),
                    "outbound.streamSettings.realitySettings.shortId",
                ),
                fingerprint=self._optional_string(
                    reality_map.get("fingerprint"),
                    "outbound.streamSettings.realitySettings.fingerprint",
                ),
            )
        elif security not in (None, "", "none"):
            raise ValueError(f"Unsupported VLESS stream security: {security!r}")

        name = (
            self._optional_string(document.get("remarks"), "remarks")
            or self._optional_string(outbound.get("tag"), "outbound.tag")
            or address
        )

        return VlessServerConfig(
            name=name,
            address=address,
            port=port,
            uuid=uuid,
            flow=flow,
            network=network,
            reality=reality,
        )

    @staticmethod
    def _load(source: str | Mapping[str, Any]) -> Mapping[str, Any]:
        if isinstance(source, str):
            try:
                value = json.loads(source)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid VLESS JSON: {exc.msg}") from exc
        else:
            value = source

        if not isinstance(value, Mapping):
            raise ValueError("VLESS JSON root must be an object")
        return value

    @staticmethod
    def _find_vless_outbound(
        document: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        outbounds = document.get("outbounds")
        if not isinstance(outbounds, list) or not outbounds:
            raise ValueError("VLESS JSON must contain non-empty outbounds")

        vless = [
            item
            for item in outbounds
            if isinstance(item, Mapping) and item.get("protocol") == "vless"
        ]
        if not vless:
            raise ValueError("No VLESS outbound found")
        if len(vless) > 1:
            raise ValueError("Multiple VLESS outbounds are not supported yet")
        return vless[0]

    @staticmethod
    def _mapping(value: object, field: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{field} must be an object")
        return value

    @staticmethod
    def _required_string(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        return value.strip()

    @staticmethod
    def _optional_string(value: object, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string")
        value = value.strip()
        return value or None

    @staticmethod
    def _required_port(value: object, field: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{field} must be an integer port")
        try:
            port = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} must be an integer port") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{field} must be between 1 and 65535")
        return port
