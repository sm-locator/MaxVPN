from datetime import datetime, timezone
from unittest.mock import Mock

from backend.infrastructure.wireguard.ssh_amneziawg_runtime_health import (
    ExpectedAmneziaWGPeer,
    SSHAmneziaWGRuntimeHealth,
)
from backend.models.command_result import CommandResult
from backend.ports.remote_command_executor import RemoteCommandExecutor

INTERFACE_UP = (
    "18: WireGuard: <POINTOPOINT,NOARP,UP,LOWER_UP> "
    "mtu 1380 qdisc noqueue state UNKNOWN\n"
    "    link/none\n"
)

PUBLIC_KEY = "WH9gAzRU4TtXs4/GOLvay1CxEuSb/SzFHqHhH8ZV0lA="

ENDPOINT = "194.26.192.36:39743"


def make_checker(executor):
    return SSHAmneziaWGRuntimeHealth(
        executor=executor,
        interface_name="WireGuard",
        expected_peer=ExpectedAmneziaWGPeer(
            public_key=PUBLIC_KEY,
            endpoint=ENDPOINT,
        ),
    )


def make_dump(
    *,
    handshake: int = 1787301000,
    rx: int = 2597152,
    tx: int = 2125824,
    endpoint: str = ENDPOINT,
) -> str:
    interface = (
        "GIWOjAPB3hZqj8o5Aa+m8T8DfcxNFmQgnHY6nsB+y2w= "
        "vMLrY8dNcrDXhuAflaB2YcE5VSTLs9rgZbYc8McpoTo= "
        "43095 5 49 998 17 110 0 0 "
        "1597513488-1927637527 "
        "1959162374-2134706886 "
        "2135520142-2141053315 "
        "2143034152-2146422435 "
        "(null) (null) (null) (null) (null) off"
    )

    peer = (
        f"{PUBLIC_KEY} "
        "4ZYg+BqMsZJXD8eocELGqR4zdou4XW9WkZeGBZOe8Jk= "
        f"{endpoint} 0.0.0.0/0 "
        f"{handshake} {rx} {tx} 25"
    )

    return f"{interface}\n{peer}\n"


def test_check_parses_real_awg_dump_format():
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout=INTERFACE_UP,
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=make_dump(),
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=("194.26.192.36 via 46.48.56.1 dev eth1 src 46.48.56.64\n"),
            stderr="",
            returncode=0,
        ),
    ]

    health = make_checker(executor).check()

    assert health.interface_exists is True
    assert health.interface_up is True
    assert health.expected_peer_found is True
    assert health.expected_endpoint is True
    assert health.listen_port == 43095

    assert health.latest_handshake == datetime.fromtimestamp(
        1787301000,
        tz=timezone.utc,
    )

    assert health.rx_bytes == 2597152
    assert health.tx_bytes == 2125824
    assert health.endpoint_route_ok is True
    assert health.healthy is True
    assert health.reason is None


def test_zero_handshake_is_reported_without_rx():
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout=INTERFACE_UP,
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=make_dump(
                handshake=0,
                rx=0,
                tx=1323280,
            ),
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=("194.26.192.36 via 46.48.56.1 dev eth1 src 46.48.56.64\n"),
            stderr="",
            returncode=0,
        ),
    ]

    health = make_checker(executor).check()

    assert health.latest_handshake is None
    assert health.rx_bytes == 0
    assert health.tx_bytes == 1323280
    assert health.healthy is False
    assert health.reason == "no_handshake"


def test_endpoint_mismatch_is_detected():
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout=INTERFACE_UP,
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=make_dump(
                endpoint="45.141.215.26:51820",
            ),
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=("194.26.192.36 via 46.48.56.1 dev eth1 src 46.48.56.64\n"),
            stderr="",
            returncode=0,
        ),
    ]

    health = make_checker(executor).check()

    assert health.expected_endpoint is False
    assert health.healthy is False
    assert health.reason == "endpoint_mismatch"


def test_endpoint_route_must_use_wan():
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        CommandResult(
            stdout=INTERFACE_UP,
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=make_dump(),
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout=("194.26.192.36 dev WireGuard src 10.9.9.200\n"),
            stderr="",
            returncode=0,
        ),
    ]

    health = make_checker(executor).check()

    assert health.endpoint_route_ok is False
    assert health.healthy is False
    assert health.reason == "endpoint_route_not_via_wan"
