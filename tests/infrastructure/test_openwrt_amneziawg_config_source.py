from unittest.mock import Mock

import pytest

from backend.infrastructure.openwrt.openwrt_amneziawg_config_source import (
    OpenWrtAmneziaWGConfigSource,
)
from backend.models.command_result import CommandResult


def make_executor(values: dict[str, str]) -> Mock:
    executor = Mock()

    def run(command: list[str]) -> CommandResult:
        key = command[2]

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
        "network.WireGuard.private_key": "interface-private",
        "network.WireGuard.addresses": "10.8.0.26/24",
        "network.WireGuard.mtu": "1380",
        "network.WireGuard.awg_jc": "5",
        "network.WireGuard.awg_jmin": "2",
        "network.WireGuard.awg_jmax": "9",
        "network.WireGuard.awg_s1": "0",
        "network.WireGuard.awg_s2": "0",
        "network.WireGuard.awg_h1": "1",
        "network.WireGuard.awg_h2": "2",
        "network.WireGuard.awg_h3": "3",
        "network.WireGuard.awg_h4": "4",
        ("network.@amneziawg_WireGuard[0].public_key"): "peer-public",
        ("network.@amneziawg_WireGuard[0].preshared_key"): "peer-preshared",
        ("network.@amneziawg_WireGuard[0].allowed_ips"): "0.0.0.0/0",
        ("network.@amneziawg_WireGuard[0].endpoint_host"): "109.172.55.99",
        ("network.@amneziawg_WireGuard[0].endpoint_port"): "51820",
        ("network.@amneziawg_WireGuard[0].persistent_keepalive"): "25",
    }


def test_read_builds_amneziawg_config() -> None:
    executor = make_executor(make_values())
    source = OpenWrtAmneziaWGConfigSource(executor)

    config = source.read()

    assert config.interface.private_key == "interface-private"
    assert config.interface.address == "10.8.0.26/24"
    assert config.interface.mtu == 1380
    assert config.interface.jc == 5
    assert config.interface.jmin == 2
    assert config.interface.jmax == 9
    assert config.interface.s1 == 0
    assert config.interface.s2 == 0
    assert config.interface.h1 == "1"
    assert config.interface.h2 == "2"
    assert config.interface.h3 == "3"
    assert config.interface.h4 == "4"

    assert config.peer.public_key == "peer-public"
    assert config.peer.preshared_key == "peer-preshared"
    assert config.peer.allowed_ips == ("0.0.0.0/0",)
    assert config.peer.endpoint == "109.172.55.99:51820"
    assert config.peer.persistent_keepalive == 25


def test_optional_integer_can_be_empty() -> None:
    values = make_values()
    values["network.WireGuard.awg_jmin"] = ""

    executor = make_executor(values)
    source = OpenWrtAmneziaWGConfigSource(executor)

    config = source.read()

    assert config.interface.jmin is None


def test_invalid_integer_is_rejected() -> None:
    values = make_values()
    values["network.WireGuard.mtu"] = "invalid"

    executor = make_executor(values)
    source = OpenWrtAmneziaWGConfigSource(executor)

    with pytest.raises(
        RuntimeError,
        match="uci_integer_invalid",
    ):
        source.read()


def test_uci_command_failure_is_rejected() -> None:
    values = make_values()
    values.pop("network.WireGuard.private_key")

    executor = make_executor(values)
    source = OpenWrtAmneziaWGConfigSource(executor)

    with pytest.raises(
        RuntimeError,
        match="uci_get_failed",
    ):
        source.read()


def test_empty_required_value_is_rejected() -> None:
    values = make_values()
    values["network.WireGuard.addresses"] = ""

    executor = make_executor(values)
    source = OpenWrtAmneziaWGConfigSource(executor)

    with pytest.raises(
        RuntimeError,
        match="uci_value_empty",
    ):
        source.read()


def test_missing_optional_s3_s4_are_allowed() -> None:
    values = make_values()

    executor = make_executor(values)
    source = OpenWrtAmneziaWGConfigSource(executor)

    config = source.read()

    assert config.interface.s3 is None
    assert config.interface.s4 is None


def test_s3_s4_are_read_when_present() -> None:
    values = make_values()

    values["network.WireGuard.awg_s3"] = "0"
    values["network.WireGuard.awg_s4"] = "0"

    executor = make_executor(values)
    source = OpenWrtAmneziaWGConfigSource(executor)

    config = source.read()

    assert config.interface.s3 == 0
    assert config.interface.s4 == 0
