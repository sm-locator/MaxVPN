from __future__ import annotations

from typing import Any

from backend.models.vless_config import VlessServerConfig


class VlessSingBoxRenderer:
    """Render a MaxVPN VLESS server into a sing-box outbound."""

    def render_outbound(
        self,
        config: VlessServerConfig,
        *,
        tag: str = "vless",
    ) -> dict[str, Any]:
        if config.network != "tcp":
            raise ValueError(
                f"Unsupported VLESS network for current renderer: {config.network!r}"
            )

        outbound: dict[str, Any] = {
            "type": "vless",
            "tag": tag,
            "server": config.address,
            "server_port": config.port,
            "uuid": config.uuid,
            # Do not set sing-box's outbound "network" to tcp here. The VLESS
            # URI's type=tcp describes the proxy transport; sing-box's outbound
            # network field restricts destination traffic. Restricting it to tcp
            # makes urltest reject the outbound for UDP client traffic.
            # XUDP carries UDP packets over the VLESS stream (for Xray-compatible
            # peers); sing-box defaults to xudp, but declare it explicitly.
            "packet_encoding": "xudp",
        }

        if config.flow:
            outbound["flow"] = config.flow

        if config.reality is not None:
            tls: dict[str, Any] = {
                "enabled": True,
                "server_name": config.reality.server_name,
                "reality": {
                    "enabled": True,
                    "public_key": config.reality.public_key,
                    "short_id": config.reality.short_id,
                },
            }

            if config.reality.fingerprint:
                tls["utls"] = {
                    "enabled": True,
                    "fingerprint": config.reality.fingerprint,
                }

            outbound["tls"] = tls

        return outbound
