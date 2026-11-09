from __future__ import annotations

import shlex

from backend.models.amneziawg_config import AmneziaWGConfig
from backend.ports.amneziawg_config_persistence import AmneziaWGConfigPersistence
from backend.ports.remote_command_executor import RemoteCommandExecutor


class OpenWrtAmneziaWGConfigPersistence(AmneziaWGConfigPersistence):
    """Persist the MaxVPN AmneziaWG profile into the existing OpenWrt UCI sections."""

    INTERFACE_SECTION = "network.WireGuard"
    PEER_SECTION = "network.@amneziawg_WireGuard[0]"

    def __init__(
        self,
        executor: RemoteCommandExecutor,
    ) -> None:
        self._executor = executor

    def persist(self, config: AmneziaWGConfig) -> None:
        host, port = self._split_endpoint(config.peer.endpoint)
        delete_commands = [
            self._delete(self.INTERFACE_SECTION, field)
            for field, value in (
                ("mtu", config.interface.mtu),
                ("dns", config.interface.dns),
                ("awg_jc", config.interface.jc),
                ("awg_jmin", config.interface.jmin),
                ("awg_jmax", config.interface.jmax),
                ("awg_s1", config.interface.s1),
                ("awg_s2", config.interface.s2),
                ("awg_s3", config.interface.s3),
                ("awg_s4", config.interface.s4),
                ("awg_h1", config.interface.h1),
                ("awg_h2", config.interface.h2),
                ("awg_h3", config.interface.h3),
                ("awg_h4", config.interface.h4),
                ("awg_i1", config.interface.i1),
                ("awg_i2", config.interface.i2),
                ("awg_i3", config.interface.i3),
                ("awg_i4", config.interface.i4),
                ("awg_i5", config.interface.i5),
            )
            if value is None
        ]
        delete_commands.extend(
            [
                self._delete(self.PEER_SECTION, "allowed_ips"),
            ]
        )
        if config.peer.preshared_key is None:
            delete_commands.append(self._delete(self.PEER_SECTION, "preshared_key"))
        if config.peer.persistent_keepalive is None:
            delete_commands.append(
                self._delete(self.PEER_SECTION, "persistent_keepalive")
            )

        script = "set -eu; " + "; ".join(
            f"uci -q delete {command} || true" for command in delete_commands
        )
        script += "; uci batch"

        batch: list[str] = [
            self._set(self.INTERFACE_SECTION, "proto", "amneziawg"),
            self._set(
                self.INTERFACE_SECTION,
                "private_key",
                config.interface.private_key,
            ),
            self._set(
                self.INTERFACE_SECTION,
                "addresses",
                config.interface.address,
            ),
        ]

        for field, value in (
            ("mtu", config.interface.mtu),
            ("dns", config.interface.dns),
            ("awg_jc", config.interface.jc),
            ("awg_jmin", config.interface.jmin),
            ("awg_jmax", config.interface.jmax),
            ("awg_s1", config.interface.s1),
            ("awg_s2", config.interface.s2),
            ("awg_s3", config.interface.s3),
            ("awg_s4", config.interface.s4),
            ("awg_h1", config.interface.h1),
            ("awg_h2", config.interface.h2),
            ("awg_h3", config.interface.h3),
            ("awg_h4", config.interface.h4),
            ("awg_i1", config.interface.i1),
            ("awg_i2", config.interface.i2),
            ("awg_i3", config.interface.i3),
            ("awg_i4", config.interface.i4),
            ("awg_i5", config.interface.i5),
        ):
            if value is not None:
                batch.append(self._set(self.INTERFACE_SECTION, field, value))

        for value in config.peer.allowed_ips:
            batch.append(self._add_list(self.PEER_SECTION, "allowed_ips", value))

        batch.extend(
            [
                self._set(self.PEER_SECTION, "public_key", config.peer.public_key),
                *(
                    [
                        self._set(
                            self.PEER_SECTION,
                            "preshared_key",
                            config.peer.preshared_key,
                        )
                    ]
                    if config.peer.preshared_key is not None
                    else []
                ),
                *(
                    [
                        self._set(
                            self.PEER_SECTION,
                            "persistent_keepalive",
                            config.peer.persistent_keepalive,
                        )
                    ]
                    if config.peer.persistent_keepalive is not None
                    else []
                ),
                self._set(self.PEER_SECTION, "endpoint_host", host),
                self._set(self.PEER_SECTION, "endpoint_port", port),
                "commit network",
            ]
        )

        result = self._executor.run(
            ["sh", "-c", script],
            stdin="\n".join(batch) + "\n",
        )

        if result.returncode != 0:
            raise RuntimeError(
                "OpenWrt AmneziaWG persistent configuration failed: "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )

    @staticmethod
    def _set(section: str, option: str, value: object) -> str:
        return f"set {section}.{option}={shlex.quote(str(value))}"

    @staticmethod
    def _add_list(section: str, option: str, value: object) -> str:
        return f"add_list {section}.{option}={shlex.quote(str(value))}"

    @staticmethod
    def _delete(section: str, option: str) -> str:
        return f"{section}.{option}"

    @staticmethod
    def _split_endpoint(endpoint: str) -> tuple[str, int]:
        value = endpoint.strip()
        if not value:
            raise ValueError("AmneziaWG endpoint must not be empty")

        if value.startswith("["):
            close = value.find("]")
            if close <= 1 or len(value) <= close + 2 or value[close + 1] != ":":
                raise ValueError(f"Invalid AmneziaWG endpoint: {endpoint!r}")
            host = value[1:close]
            port_text = value[close + 2 :]
        else:
            host, separator, port_text = value.rpartition(":")
            if not separator or not host or not port_text:
                raise ValueError(f"Invalid AmneziaWG endpoint: {endpoint!r}")

        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError(f"Invalid AmneziaWG endpoint: {endpoint!r}") from exc

        if not 1 <= port <= 65535:
            raise ValueError(f"Invalid AmneziaWG endpoint port: {port}")

        return host, port
