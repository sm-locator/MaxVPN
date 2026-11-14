from __future__ import annotations

from backend.ports.amneziawg_runtime_config_source import (
    AmneziaWGRuntimeConfigSource,
)
from backend.ports.remote_command_executor import (
    RemoteCommandExecutor,
)


class SSHAmneziaWGRuntimeConfigSource(
    AmneziaWGRuntimeConfigSource,
):
    _IGNORED_KEYS = {
        "ListenPort",
        "AdvancedSecurity",
    }

    def __init__(
        self,
        executor: RemoteCommandExecutor,
    ) -> None:
        self._executor = executor

    def read(
        self,
        interface: str = "WireGuard",
    ) -> str:
        if not interface:
            raise ValueError("interface must not be empty")

        result = self._executor.run(
            [
                "awg",
                "showconf",
                interface,
            ],
        )

        if result.returncode != 0:
            raise RuntimeError("awg_showconf_failed")

        if not result.stdout.strip():
            raise RuntimeError("awg_showconf_empty")

        return self._normalize(result.stdout)

    @classmethod
    def _normalize(cls, text: str) -> str:
        sections: dict[str, list[str]] = {
            "Interface": [],
            "Peer": [],
        }

        section: str | None = None

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()

                if section not in sections:
                    raise RuntimeError(f"unsupported_awg_section: {section}")

                continue

            if section is None:
                raise RuntimeError("awg_config_key_before_section")

            if "=" not in line:
                raise RuntimeError(f"invalid_awg_config_line: {line}")

            key = line.split("=", 1)[0].strip()

            if key in cls._IGNORED_KEYS:
                continue

            sections[section].append(line)

        interface_order = (
            "PrivateKey",
            "Jc",
            "Jmin",
            "Jmax",
            "S1",
            "S2",
            "S3",
            "S4",
            "H1",
            "H2",
            "H3",
            "H4",
            "I1",
            "I2",
            "I3",
            "I4",
            "I5",
        )

        peer_order = (
            "PublicKey",
            "PresharedKey",
            "AllowedIPs",
            "PersistentKeepalive",
            "Endpoint",
        )

        def canonicalize(
            items: list[str],
            order: tuple[str, ...],
        ) -> list[str]:
            grouped: dict[str, list[str]] = {}

            for item in items:
                key = item.split("=", 1)[0].strip()
                grouped.setdefault(key, []).append(item)

            result: list[str] = []

            for key in order:
                result.extend(grouped.pop(key, []))

            for key in sorted(grouped):
                result.extend(grouped[key])

            return result

        interface_lines = canonicalize(
            sections["Interface"],
            interface_order,
        )
        peer_lines = canonicalize(
            sections["Peer"],
            peer_order,
        )

        return (
            "[Interface]\n" + "\n".join(interface_lines) + "\n\n"
            "[Peer]\n" + "\n".join(peer_lines) + "\n"
        )
