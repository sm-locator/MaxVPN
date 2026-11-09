from __future__ import annotations

import shlex

from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
    AmneziaWGPeer,
)
from backend.ports.amneziawg_config_source import (
    AmneziaWGConfigSource,
)
from backend.ports.remote_command_executor import (
    RemoteCommandExecutor,
)


class OpenWrtAmneziaWGConfigSource(
    AmneziaWGConfigSource,
):
    def __init__(
        self,
        executor: RemoteCommandExecutor,
        interface: str = "WireGuard",
    ) -> None:
        if not interface:
            raise ValueError("interface must not be empty")

        self._executor = executor
        self._interface = interface

    def read(self) -> AmneziaWGConfig:
        prefix = f"network.{self._interface}"
        peer_prefix = f"network.@amneziawg_{self._interface}[0]"

        private_key = self._get(
            f"{prefix}.private_key",
        )
        address = self._get(
            f"{prefix}.addresses",
        )

        mtu = self._get_optional_int(
            f"{prefix}.mtu",
        )
        dns = self._get_optional(
            f"{prefix}.dns",
        )

        interface = AmneziaWGInterface(
            private_key=private_key,
            address=address,
            mtu=mtu,
            dns=dns,
            jc=self._get_optional_int(
                f"{prefix}.awg_jc",
            ),
            jmin=self._get_optional_int(
                f"{prefix}.awg_jmin",
            ),
            jmax=self._get_optional_int(
                f"{prefix}.awg_jmax",
            ),
            s1=self._get_optional_int(
                f"{prefix}.awg_s1",
            ),
            s2=self._get_optional_int(
                f"{prefix}.awg_s2",
            ),
            s3=self._get_optional_int(
                f"{prefix}.awg_s3",
            ),
            s4=self._get_optional_int(
                f"{prefix}.awg_s4",
            ),
            h1=self._get_optional(
                f"{prefix}.awg_h1",
            ),
            h2=self._get_optional(
                f"{prefix}.awg_h2",
            ),
            h3=self._get_optional(
                f"{prefix}.awg_h3",
            ),
            h4=self._get_optional(
                f"{prefix}.awg_h4",
            ),
            i1=self._get_optional(f"{prefix}.awg_i1"),
            i2=self._get_optional(f"{prefix}.awg_i2"),
            i3=self._get_optional(f"{prefix}.awg_i3"),
            i4=self._get_optional(f"{prefix}.awg_i4"),
            i5=self._get_optional(f"{prefix}.awg_i5"),
        )

        peer = AmneziaWGPeer(
            public_key=self._get(
                f"{peer_prefix}.public_key",
            ),
            preshared_key=self._get_optional(
                f"{peer_prefix}.preshared_key",
            ),
            allowed_ips=self._get_list(
                f"{peer_prefix}.allowed_ips",
            ),
            endpoint=(
                f"{self._get(f'{peer_prefix}.endpoint_host')}:"
                f"{self._get(f'{peer_prefix}.endpoint_port')}"
            ),
            persistent_keepalive=self._get_optional_int(
                f"{peer_prefix}.persistent_keepalive",
            ),
        )

        return AmneziaWGConfig(
            interface=interface,
            peer=peer,
        )

    def _run_uci(self, key: str):
        result = self._executor.run(
            ["uci", "get", key],
        )

        if result.returncode != 0:
            raise RuntimeError(f"uci_get_failed: {key}")

        return result.stdout.strip()

    def _get(self, key: str) -> str:
        value = self._run_uci(key)

        if not value:
            raise RuntimeError(f"uci_value_empty: {key}")

        return value

    def _get_optional(self, key: str) -> str | None:
        result = self._executor.run(
            ["uci", "get", key],
        )

        if result.returncode != 0:
            if "Entry not found" in result.stderr:
                return None

            raise RuntimeError(f"uci_get_failed: {key}")

        value = result.stdout.strip()
        return value or None

    def _get_list(self, key: str) -> tuple[str, ...]:
        value = self._run_uci(key)

        if not value:
            return ()

        return tuple(shlex.split(value))

    def _get_optional_int(self, key: str) -> int | None:
        result = self._executor.run(
            ["uci", "get", key],
        )

        if result.returncode != 0:
            if "Entry not found" in result.stderr:
                return None

            raise RuntimeError(f"uci_get_failed: {key}")

        value = result.stdout.strip()

        if not value:
            return None

        try:
            return int(value)
        except ValueError as exc:
            raise RuntimeError(f"uci_integer_invalid: {key}") from exc

    def _get_int(self, key: str) -> int | None:
        value = self._run_uci(key)

        if not value:
            return None

        try:
            return int(value)
        except ValueError as exc:
            raise RuntimeError(f"uci_integer_invalid: {key}") from exc
