from datetime import datetime, timezone
from unittest.mock import patch

from backend.infrastructure.wireguard.system_amneziawg_health_checker import (
    SystemAmneziaWGHealthChecker,
)
from backend.models.wireguard_health import WireGuardHealthStatus

INTERFACE_UP_OUTPUT = (
    "17: WireGuard: <POINTOPOINT,NOARP,UP,LOWER_UP> "
    "mtu 1380 qdisc noqueue state UNKNOWN\n"
    "    link/none\n"
)

AWG_DUMP = (
    "oBGphdOhJXLWTd/qgAcXkiEPVZio/mfa6rr66YV9V3E= "
    "pBGNU9zr9xfiXae6IUYPaVihQ6KQyU/4HkjMqZc20SA= "
    "45121 5 2 90 0 0 0 1 2 3 4 "
    "(null) (null) (null) (null) (null) off\n"
    "GUdxiwBvCKYlZL7NjGfek1vES+JuTl1pogI2CWxNoVo= "
    "2DlNQOBs5a73uOu4QM2hHHoYW3xNUyuOCEax48If0/g= "
    "45.141.215.26:51820 0.0.0.0/0,::/0 "
    "1786781816 39983804496 2157289651 25\n"
)


def test_check_reads_healthy_amneziawg_state() -> None:
    checker = SystemAmneziaWGHealthChecker(
        interface_name="WireGuard",
    )

    def run_side_effect(command, **kwargs):
        if command[:3] == ["ip", "link", "show"]:
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": INTERFACE_UP_OUTPUT,
                    "stderr": "",
                },
            )()

        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": AWG_DUMP,
                "stderr": "",
            },
        )()

    with patch(
        "backend.infrastructure.wireguard.system_amneziawg_health_checker.subprocess.run",
        side_effect=run_side_effect,
    ):
        health = checker.check()

    assert health.interface_exists is True
    assert health.interface_up is True
    assert health.listen_port == 45121
    assert health.peer_count == 1
    assert health.latest_handshake == datetime.fromtimestamp(
        1786781816,
        tz=timezone.utc,
    )
    assert health.rx_bytes == 39983804496
    assert health.tx_bytes == 2157289651
    assert health.status is WireGuardHealthStatus.UNKNOWN
    assert health.reason is None


def test_check_reports_missing_interface() -> None:
    checker = SystemAmneziaWGHealthChecker(
        interface_name="WireGuard",
    )

    with patch(
        "backend.infrastructure.wireguard.system_amneziawg_health_checker.subprocess.run"
    ) as run:
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = "Device not found"

        health = checker.check()

    assert health.interface_exists is False
    assert health.interface_up is False
    assert health.status is WireGuardHealthStatus.FAILED
    assert health.reason == "interface_not_found"

    run.assert_called_once()


def test_check_reports_interface_down() -> None:
    checker = SystemAmneziaWGHealthChecker(
        interface_name="WireGuard",
    )

    interface_down_output = (
        "17: WireGuard: <POINTOPOINT,NOARP> "
        "mtu 1380 qdisc noqueue state DOWN\n"
        "    link/none\n"
    )

    def run_side_effect(command, **kwargs):
        if command[:3] == ["ip", "link", "show"]:
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": interface_down_output,
                    "stderr": "",
                },
            )()

        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": AWG_DUMP,
                "stderr": "",
            },
        )()

    with patch(
        "backend.infrastructure.wireguard.system_amneziawg_health_checker.subprocess.run",
        side_effect=run_side_effect,
    ):
        health = checker.check()

    assert health.interface_exists is True
    assert health.interface_up is False
    assert health.status is WireGuardHealthStatus.FAILED
    assert health.reason == "interface_down"


def test_check_reports_no_peers() -> None:
    checker = SystemAmneziaWGHealthChecker(
        interface_name="WireGuard",
    )

    interface_only_dump = (
        "oBGphdOhJXLWTd/qgAcXkiEPVZio/mfa6rr66YV9V3E= "
        "pBGNU9zr9xfiXae6IUYPaVihQ6KQyU/4HkjMqZc20SA= "
        "45121 5 2 90 0 0 0 1 2 3 4 "
        "(null) (null) (null) (null) (null) off\n"
    )

    def run_side_effect(command, **kwargs):
        if command[:3] == ["ip", "link", "show"]:
            return type(
                "Result",
                (),
                {
                    "returncode": 0,
                    "stdout": INTERFACE_UP_OUTPUT,
                    "stderr": "",
                },
            )()

        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": interface_only_dump,
                "stderr": "",
            },
        )()

    with patch(
        "backend.infrastructure.wireguard.system_amneziawg_health_checker.subprocess.run",
        side_effect=run_side_effect,
    ):
        health = checker.check()

    assert health.peer_count == 0
    assert health.latest_handshake is None
    assert health.status is WireGuardHealthStatus.DEGRADED
    assert health.reason == "no_peers"


def test_parse_dump_aggregates_multiple_peers() -> None:
    dump = (
        "private public 51820 5 2 90 0 0 0 1 2 3 4 "
        "(null) (null) (null) (null) (null) off\n"
        "peer1 ps1 endpoint1 allowed1 100 10 20 25\n"
        "peer2 ps2 endpoint2 allowed2 200 30 40 25\n"
    )

    (
        listen_port,
        peer_count,
        latest_handshake,
        rx_bytes,
        tx_bytes,
    ) = SystemAmneziaWGHealthChecker._parse_dump(dump)

    assert listen_port == 51820
    assert peer_count == 2
    assert latest_handshake == datetime.fromtimestamp(
        200,
        tz=timezone.utc,
    )
    assert rx_bytes == 40
    assert tx_bytes == 60
