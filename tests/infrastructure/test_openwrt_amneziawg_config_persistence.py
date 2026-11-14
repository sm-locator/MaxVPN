from unittest.mock import Mock

import pytest

from backend.infrastructure.openwrt.openwrt_amneziawg_config_persistence import (
    OpenWrtAmneziaWGConfigPersistence,
)
from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
    AmneziaWGPeer,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


def make_config() -> AmneziaWGConfig:
    return AmneziaWGConfig(
        interface=AmneziaWGInterface(
            private_key="private-key",
            address="10.8.0.20/24",
            mtu=1380,
            dns="1.1.1.1",
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=None,
            s4=None,
            h1="1",
            h2="2",
            h3="3",
            h4="4",
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=AmneziaWGPeer(
            public_key="public-key",
            preshared_key="preshared-key",
            allowed_ips=("0.0.0.0/0", "::/0"),
            endpoint="109.172.55.200:51820",
            persistent_keepalive=25,
        ),
    )


def make_executor() -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(returncode=0, stdout="", stderr="")
    return executor


def test_persist_writes_only_amneziawg_sections() -> None:
    executor = make_executor()
    persistence = OpenWrtAmneziaWGConfigPersistence(executor)

    persistence.persist(make_config())

    call = executor.run.call_args
    command = call.args[0]
    stdin = call.kwargs["stdin"]
    assert command[:2] == ["sh", "-c"]
    script = command[2]

    assert "network.WireGuard" in script
    assert "network.@amneziawg_WireGuard[0]" in script
    assert "uci batch" in script
    assert "commit network" in stdin
    assert "ifup" not in script
    assert "ifdown" not in script
    assert "network reload" not in script
    assert "firewall reload" not in script
    assert "network.@wireguard_WireGuard[0]" not in script
    assert "private-key" in stdin
    assert "preshared-key" in stdin
    assert "private-key" not in " ".join(command)
    assert "preshared-key" not in " ".join(command)


def test_persist_replaces_allowed_ips_as_a_list() -> None:
    executor = make_executor()
    persistence = OpenWrtAmneziaWGConfigPersistence(executor)

    persistence.persist(make_config())

    call = executor.run.call_args
    script = call.args[0][2]
    stdin = call.kwargs["stdin"]
    assert "uci -q delete network.@amneziawg_WireGuard[0].allowed_ips || true" in script
    assert "add_list network.@amneziawg_WireGuard[0].allowed_ips=0.0.0.0/0" in stdin
    assert "add_list network.@amneziawg_WireGuard[0].allowed_ips=::/0" in stdin


def test_persist_unsets_optional_values() -> None:
    executor = make_executor()
    persistence = OpenWrtAmneziaWGConfigPersistence(executor)

    config = make_config()
    config = AmneziaWGConfig(
        interface=AmneziaWGInterface(
            private_key=config.interface.private_key,
            address=config.interface.address,
        ),
        peer=AmneziaWGPeer(
            public_key=config.peer.public_key,
            allowed_ips=config.peer.allowed_ips,
            endpoint=config.peer.endpoint,
        ),
    )

    persistence.persist(config)
    script = executor.run.call_args.args[0][2]

    assert "uci -q delete network.WireGuard.mtu || true" in script
    assert "uci -q delete network.WireGuard.dns || true" in script
    assert (
        "uci -q delete network.@amneziawg_WireGuard[0].preshared_key || true" in script
    )


@pytest.mark.parametrize(
    ("endpoint", "host", "port"),
    [
        ("109.172.55.200:51820", "109.172.55.200", 51820),
        ("vpn.example.com:443", "vpn.example.com", 443),
        ("[2001:db8::1]:51820", "2001:db8::1", 51820),
    ],
)
def test_split_endpoint(endpoint: str, host: str, port: int) -> None:
    assert OpenWrtAmneziaWGConfigPersistence._split_endpoint(endpoint) == (host, port)


def test_split_endpoint_rejects_invalid_endpoint() -> None:
    with pytest.raises(ValueError):
        OpenWrtAmneziaWGConfigPersistence._split_endpoint("not-an-endpoint")
