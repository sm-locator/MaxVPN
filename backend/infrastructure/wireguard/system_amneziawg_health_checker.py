from __future__ import annotations

import subprocess
from datetime import datetime, timezone

from backend.models.wireguard_health import (
    WireGuardHealth,
    WireGuardHealthStatus,
)
from backend.ports.wireguard_health_checker import WireGuardHealthChecker


class SystemAmneziaWGHealthChecker(WireGuardHealthChecker):
    """
    Reads the runtime state of an AmneziaWG interface using system commands.
    """

    def __init__(
        self,
        interface_name: str,
        awg_binary: str = "awg",
        ip_binary: str = "ip",
    ) -> None:
        self._interface_name = interface_name
        self._awg_binary = awg_binary
        self._ip_binary = ip_binary

    def check(self) -> WireGuardHealth:
        checked_at = datetime.now(timezone.utc)

        interface_result = subprocess.run(
            [
                self._ip_binary,
                "link",
                "show",
                "dev",
                self._interface_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if interface_result.returncode != 0:
            return WireGuardHealth(
                interface_exists=False,
                interface_up=False,
                listen_port=None,
                peer_count=0,
                latest_handshake=None,
                rx_bytes=0,
                tx_bytes=0,
                status=WireGuardHealthStatus.FAILED,
                reason="interface_not_found",
                checked_at=checked_at,
            )

        interface_up = self._is_interface_up(interface_result.stdout)

        dump_result = subprocess.run(
            [
                self._awg_binary,
                "show",
                self._interface_name,
                "dump",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if dump_result.returncode != 0:
            return WireGuardHealth(
                interface_exists=True,
                interface_up=interface_up,
                listen_port=None,
                peer_count=0,
                latest_handshake=None,
                rx_bytes=0,
                tx_bytes=0,
                status=WireGuardHealthStatus.FAILED,
                reason="awg_dump_failed",
                checked_at=checked_at,
            )

        try:
            (
                listen_port,
                peer_count,
                latest_handshake,
                rx_bytes,
                tx_bytes,
            ) = self._parse_dump(dump_result.stdout)
        except ValueError:
            return WireGuardHealth(
                interface_exists=True,
                interface_up=interface_up,
                listen_port=None,
                peer_count=0,
                latest_handshake=None,
                rx_bytes=0,
                tx_bytes=0,
                status=WireGuardHealthStatus.FAILED,
                reason="invalid_awg_dump",
                checked_at=checked_at,
            )

        status, reason = self._determine_status(
            interface_up=interface_up,
            peer_count=peer_count,
            latest_handshake=latest_handshake,
        )

        return WireGuardHealth(
            interface_exists=True,
            interface_up=interface_up,
            listen_port=listen_port,
            peer_count=peer_count,
            latest_handshake=latest_handshake,
            rx_bytes=rx_bytes,
            tx_bytes=tx_bytes,
            status=status,
            reason=reason,
            checked_at=checked_at,
        )

    @staticmethod
    def _is_interface_up(output: str) -> bool:
        first_line = output.splitlines()[0] if output.splitlines() else ""

        if "<" not in first_line or ">" not in first_line:
            return False

        flags = first_line.split("<", 1)[1].split(">", 1)[0]
        return "UP" in {flag.strip() for flag in flags.split(",")}

    @staticmethod
    def _parse_dump(
        output: str,
    ) -> tuple[int, int, datetime | None, int, int]:
        lines = [line for line in output.splitlines() if line.strip()]

        if not lines:
            raise ValueError("AmneziaWG dump is empty.")

        interface_fields = lines[0].split()

        if len(interface_fields) < 3:
            raise ValueError("Invalid AmneziaWG interface dump.")

        try:
            listen_port = int(interface_fields[2])
        except ValueError as exc:
            raise ValueError("Invalid AmneziaWG listen port.") from exc

        peer_count = 0
        latest_handshake_timestamp = 0
        rx_bytes = 0
        tx_bytes = 0

        for line in lines[1:]:
            fields = line.split()

            if len(fields) != 8:
                raise ValueError("Invalid AmneziaWG peer dump.")

            try:
                handshake_timestamp = int(fields[4])
                peer_rx_bytes = int(fields[5])
                peer_tx_bytes = int(fields[6])
            except ValueError as exc:
                raise ValueError("Invalid AmneziaWG peer metrics.") from exc

            peer_count += 1
            latest_handshake_timestamp = max(
                latest_handshake_timestamp,
                handshake_timestamp,
            )
            rx_bytes += peer_rx_bytes
            tx_bytes += peer_tx_bytes

        latest_handshake = (
            datetime.fromtimestamp(
                latest_handshake_timestamp,
                tz=timezone.utc,
            )
            if latest_handshake_timestamp > 0
            else None
        )

        return (
            listen_port,
            peer_count,
            latest_handshake,
            rx_bytes,
            tx_bytes,
        )

    @staticmethod
    def _determine_status(
        *,
        interface_up: bool,
        peer_count: int,
        latest_handshake: datetime | None,
    ) -> tuple[WireGuardHealthStatus, str | None]:
        if not interface_up:
            return WireGuardHealthStatus.FAILED, "interface_down"

        if peer_count == 0:
            return WireGuardHealthStatus.DEGRADED, "no_peers"

        if latest_handshake is None:
            return WireGuardHealthStatus.DEGRADED, "no_handshake"

        return WireGuardHealthStatus.UNKNOWN, None
