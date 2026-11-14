from __future__ import annotations

from backend.models.amneziawg_config import AmneziaWGConfig


class AmneziaWGConfigRenderer:
    """Renders parsed AmneziaWG configurations."""

    def render_full(self, config: AmneziaWGConfig) -> str:
        interface = config.interface
        peer = config.peer

        lines = [
            "[Interface]",
            f"PrivateKey = {interface.private_key}",
            f"Address = {interface.address}",
        ]

        self._append_optional(lines, "DNS", interface.dns)
        self._append_optional(lines, "MTU", interface.mtu)

        self._append_interface_awg(lines, interface)

        lines.extend(
            [
                "",
                "[Peer]",
                f"PublicKey = {peer.public_key}",
            ]
        )

        self._append_optional(lines, "PresharedKey", peer.preshared_key)

        for allowed_ip in peer.allowed_ips:
            lines.append(f"AllowedIPs = {allowed_ip}")

        self._append_optional(
            lines,
            "PersistentKeepalive",
            peer.persistent_keepalive,
        )
        lines.append(f"Endpoint = {peer.endpoint}")

        return "\n".join(lines) + "\n"

    def render_awg_runtime(self, config: AmneziaWGConfig) -> str:
        interface = config.interface
        peer = config.peer

        lines = [
            "[Interface]",
            f"PrivateKey = {interface.private_key}",
        ]

        self._append_interface_awg(lines, interface)

        lines.extend(
            [
                "",
                "[Peer]",
                f"PublicKey = {peer.public_key}",
            ]
        )

        self._append_optional(lines, "PresharedKey", peer.preshared_key)

        for allowed_ip in peer.allowed_ips:
            lines.append(f"AllowedIPs = {allowed_ip}")

        self._append_optional(
            lines,
            "PersistentKeepalive",
            peer.persistent_keepalive,
        )
        lines.append(f"Endpoint = {peer.endpoint}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _append_interface_awg(lines: list[str], interface) -> None:
        optional_awg_fields = (
            ("Jc", interface.jc),
            ("Jmin", interface.jmin),
            ("Jmax", interface.jmax),
            ("S1", interface.s1),
            ("S2", interface.s2),
            ("S3", interface.s3),
            ("S4", interface.s4),
            ("H1", interface.h1),
            ("H2", interface.h2),
            ("H3", interface.h3),
            ("H4", interface.h4),
            ("I1", interface.i1),
            ("I2", interface.i2),
            ("I3", interface.i3),
            ("I4", interface.i4),
            ("I5", interface.i5),
        )

        for key, value in optional_awg_fields:
            AmneziaWGConfigRenderer._append_optional(lines, key, value)

    @staticmethod
    def _append_optional(
        lines: list[str],
        key: str,
        value: object | None,
    ) -> None:
        if value is not None:
            lines.append(f"{key} = {value}")
