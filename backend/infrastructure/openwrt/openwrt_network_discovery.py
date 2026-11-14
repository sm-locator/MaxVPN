from __future__ import annotations

import json
import re

from backend.models.command_result import CommandResult
from backend.models.openwrt_network_info import OpenWrtNetworkInfo
from backend.ports.remote_command_executor import RemoteCommandExecutor


class OpenWrtNetworkDiscovery:
    """
    Read-only discovery of the relevant OpenWrt network topology.

    No commands in this class modify routing, firewall, UCI state,
    interfaces, or services.
    """

    def __init__(self, executor: RemoteCommandExecutor) -> None:
        self._executor = executor

    def discover(self) -> OpenWrtNetworkInfo:
        lan_result = self._run(
            ["ubus", "call", "network.interface.lan", "status"],
        )
        wan_result = self._run(
            ["ubus", "call", "network.interface.wan", "status"],
        )
        route_result = self._run(
            ["ip", "-4", "route", "show", "default"],
        )
        awg_result = self._run(
            ["awg", "show"],
            check=False,
        )

        lan = self._parse_interface_status(
            lan_result,
            "lan",
        )
        wan = self._parse_interface_status(
            wan_result,
            "wan",
        )

        gateway = self._parse_default_gateway(
            route_result.stdout,
        )

        vpn_interface, vpn_endpoint = self._parse_awg(
            awg_result.stdout,
        )

        return OpenWrtNetworkInfo(
            lan_interface=lan["device"],
            lan_ipv4=lan["ipv4"],
            wan_interface=wan["device"],
            wan_ipv4=wan["ipv4"],
            wan_gateway=gateway,
            vpn_interface=vpn_interface,
            vpn_endpoint=vpn_endpoint,
        )

    def _run(
        self,
        command: list[str],
        *,
        check: bool = True,
    ) -> CommandResult:
        result = self._executor.run(command)

        if check and result.returncode != 0:
            raise RuntimeError(
                "openwrt_network_discovery_command_failed: "
                f"command={command!r}; "
                f"returncode={result.returncode}; "
                f"stderr={result.stderr!r}"
            )

        return result

    @staticmethod
    def _parse_interface_status(
        result: CommandResult,
        name: str,
    ) -> dict[str, str]:
        if result.returncode != 0:
            raise RuntimeError(f"openwrt_network_discovery_{name}_unavailable")

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"openwrt_network_discovery_invalid_{name}_json"
            ) from exc

        device = payload.get("l3_device") or payload.get("device")
        if not isinstance(device, str) or not device:
            raise RuntimeError(f"openwrt_network_discovery_{name}_device_missing")

        addresses = payload.get("ipv4-address") or []
        if not addresses:
            raise RuntimeError(f"openwrt_network_discovery_{name}_ipv4_missing")

        address = addresses[0].get("address")
        mask = addresses[0].get("mask")

        if not isinstance(address, str) or not address:
            raise RuntimeError(f"openwrt_network_discovery_{name}_ipv4_invalid")

        if not isinstance(mask, int):
            raise RuntimeError(f"openwrt_network_discovery_{name}_mask_invalid")

        return {
            "device": device,
            "ipv4": f"{address}/{mask}",
        }

    @staticmethod
    def _parse_default_gateway(output: str) -> str:
        match = re.search(
            r"^default\s+via\s+(\S+)",
            output,
            re.MULTILINE,
        )

        if match is None:
            raise RuntimeError("openwrt_network_discovery_default_gateway_missing")

        return match.group(1)

    @staticmethod
    def _parse_awg(
        output: str,
    ) -> tuple[str | None, str | None]:
        interface_match = re.search(
            r"^interface:\s*(\S+)",
            output,
            re.MULTILINE,
        )

        endpoint_match = re.search(
            r"^\s*endpoint:\s*(\S+)",
            output,
            re.MULTILINE,
        )

        return (
            interface_match.group(1) if interface_match else None,
            endpoint_match.group(1) if endpoint_match else None,
        )
