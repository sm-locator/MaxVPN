from __future__ import annotations

from backend.infrastructure.openwrt.openwrt_amneziawg_config_source import (
    OpenWrtAmneziaWGConfigSource,
)
from backend.infrastructure.wireguard.ssh_amneziawg_runtime_config_source import (
    SSHAmneziaWGRuntimeConfigSource,
)
from backend.models.amneziawg_config import (
    AmneziaWGConfig,
)
from backend.ports.amneziawg_runtime_profile_source import (
    AmneziaWGRuntimeProfileSource,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.amneziawg_config_parser import AmneziaWGConfigParser


class OpenWrtAmneziaWGRuntimeProfileSource(
    AmneziaWGRuntimeProfileSource,
):
    def __init__(
        self,
        executor: RemoteCommandExecutor,
    ) -> None:
        self._openwrt_source = OpenWrtAmneziaWGConfigSource(
            executor=executor,
        )
        self._runtime_source = SSHAmneziaWGRuntimeConfigSource(
            executor=executor,
        )
        self._parser = AmneziaWGConfigParser()

    def read(
        self,
        interface: str = "WireGuard",
    ) -> AmneziaWGConfig:
        persistent = self._openwrt_source.read()
        runtime_text = self._runtime_source.read(interface)

        runtime = self._parser.parse(
            self._add_required_interface_metadata(
                runtime_text=runtime_text,
                address=persistent.interface.address,
                mtu=persistent.interface.mtu,
                dns=persistent.interface.dns,
            )
        )

        return runtime

    @staticmethod
    def _add_required_interface_metadata(
        runtime_text: str,
        address: str,
        mtu: int | None,
        dns: str | None,
    ) -> str:
        lines = runtime_text.splitlines()

        interface_index = lines.index("[Interface]") + 1

        metadata = [f"Address = {address}"]

        if dns is not None:
            metadata.append(f"DNS = {dns}")

        if mtu is not None:
            metadata.append(f"MTU = {mtu}")

        return (
            "\n".join(lines[:interface_index] + metadata + lines[interface_index:])
            + "\n"
        )
