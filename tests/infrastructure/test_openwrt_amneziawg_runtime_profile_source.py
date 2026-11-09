from unittest.mock import Mock

import pytest

from backend.infrastructure.openwrt.openwrt_amneziawg_runtime_profile_source import (
    OpenWrtAmneziaWGRuntimeProfileSource,
)
from backend.models.command_result import CommandResult


def make_executor(values: dict[str, str]) -> Mock:
    executor = Mock()

    def run(command: list[str]) -> CommandResult:
        key = " ".join(command)

        if key == "awg showconf WireGuard":
            return CommandResult(
                stdout="""[Interface]
PrivateKey = interface-private
Jc = 5
Jmin = 2
Jmax = 9
S1 = 0
S2 = 0
S3 = 0
S4 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4

[Peer]
PublicKey = peer-public
PresharedKey = peer-preshared
AllowedIPs = 0.0.0.0/0
Endpoint = 109.172.55.99:51820
PersistentKeepalive = 25
""",
                stderr="",
                returncode=0,
            )

        if key not in values:
            return CommandResult(
                stdout="",
                stderr="uci: Entry not found",
                returncode=1,
            )

        return CommandResult(
            stdout=values[key] + "\n",
            stderr="",
            returncode=0,
        )

    executor.run.side_effect = run
    return executor


def make_values() -> dict[str, str]:
    return {
        "uci get network.WireGuard.private_key": "interface-private",
        "uci get network.WireGuard.addresses": "10.8.0.26/24",
        "uci get network.WireGuard.mtu": "1380",
        "uci get network.WireGuard.awg_jc": "5",
        "uci get network.WireGuard.awg_jmin": "2",
        "uci get network.WireGuard.awg_jmax": "9",
        "uci get network.WireGuard.awg_s1": "0",
        "uci get network.WireGuard.awg_s2": "0",
        "uci get network.WireGuard.awg_h1": "1",
        "uci get network.WireGuard.awg_h2": "2",
        "uci get network.WireGuard.awg_h3": "3",
        "uci get network.WireGuard.awg_h4": "4",
        "uci get network.@amneziawg_WireGuard[0].public_key": "peer-public",
        "uci get network.@amneziawg_WireGuard[0].preshared_key": "peer-preshared",
        "uci get network.@amneziawg_WireGuard[0].allowed_ips": "0.0.0.0/0",
        "uci get network.@amneziawg_WireGuard[0].endpoint_host": "109.172.55.99",
        "uci get network.@amneziawg_WireGuard[0].endpoint_port": "51820",
        "uci get network.@amneziawg_WireGuard[0].persistent_keepalive": "25",
    }


def test_read_builds_effective_runtime_profile() -> None:
    executor = make_executor(make_values())

    source = OpenWrtAmneziaWGRuntimeProfileSource(executor)

    config = source.read("WireGuard")

    assert config.interface.private_key == "interface-private"
    assert config.interface.address == "10.8.0.26/24"
    assert config.interface.mtu == 1380
    assert config.interface.dns is None

    assert config.interface.jc == 5
    assert config.interface.jmin == 2
    assert config.interface.jmax == 9

    assert config.interface.s1 == 0
    assert config.interface.s2 == 0
    assert config.interface.s3 == 0
    assert config.interface.s4 == 0

    assert config.interface.h1 == "1"
    assert config.interface.h2 == "2"
    assert config.interface.h3 == "3"
    assert config.interface.h4 == "4"

    assert config.peer.public_key == "peer-public"
    assert config.peer.preshared_key == "peer-preshared"
    assert config.peer.allowed_ips == ("0.0.0.0/0",)
    assert config.peer.endpoint == "109.172.55.99:51820"
    assert config.peer.persistent_keepalive == 25


def test_read_rejects_invalid_runtime() -> None:
    executor = make_executor(make_values())

    original_run = executor.run.side_effect

    def run(command: list[str]) -> CommandResult:
        if command[:2] == ["awg", "showconf"]:
            return CommandResult(
                stdout="broken",
                stderr="",
                returncode=0,
            )

        return original_run(command)

    executor.run.side_effect = run

    source = OpenWrtAmneziaWGRuntimeProfileSource(executor)

    with pytest.raises(
        RuntimeError,
        match="awg_config_key_before_section",
    ):
        source.read("WireGuard")


def test_runtime_values_override_missing_uci_awg_values() -> None:
    executor = make_executor(make_values())

    source = OpenWrtAmneziaWGRuntimeProfileSource(executor)
    config = source.read("WireGuard")

    assert config.interface.s3 == 0
    assert config.interface.s4 == 0
