from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.models.amneziawg_runtime_health import (
    AmneziaWGRuntimeHealth,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


@dataclass(frozen=True, slots=True)
class ExpectedAmneziaWGPeer:
    public_key: str
    endpoint: str


class SSHAmneziaWGRuntimeHealth:
    """
    Read-only, machine-oriented AmneziaWG runtime health checker.

    No interface lifecycle operations are performed.
    """

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        interface_name: str,
        expected_peer: ExpectedAmneziaWGPeer,
        wan_interface: str = "eth1",
    ) -> None:
        self._executor = executor
        self._interface_name = interface_name
        self._expected_peer = expected_peer
        self._wan_interface = wan_interface

    def check(self) -> AmneziaWGRuntimeHealth:
        checked_at = datetime.now(timezone.utc)

        interface_result = self._executor.run(
            [
                "ip",
                "link",
                "show",
                "dev",
                self._interface_name,
            ]
        )

        if interface_result.returncode != 0:
            return self._failed(
                checked_at,
                "interface_not_found",
            )

        interface_up = self._is_interface_up(interface_result.stdout)

        dump_result = self._executor.run(
            [
                "awg",
                "show",
                self._interface_name,
                "dump",
            ]
        )

        if dump_result.returncode != 0:
            return self._failed(
                checked_at,
                "awg_dump_failed",
                interface_exists=True,
                interface_up=interface_up,
            )

        try:
            listen_port, peers = self._parse_dump(dump_result.stdout)
        except ValueError:
            return self._failed(
                checked_at,
                "invalid_awg_dump",
                interface_exists=True,
                interface_up=interface_up,
            )

        peer = peers.get(self._expected_peer.public_key)

        if peer is None:
            return self._result(
                checked_at=checked_at,
                interface_up=interface_up,
                listen_port=listen_port,
                reason="expected_peer_not_found",
            )

        expected_endpoint = peer.endpoint == self._expected_peer.endpoint

        endpoint_host = self._expected_peer.endpoint.rsplit(
            ":",
            1,
        )[0]

        route_result = self._executor.run(
            [
                "ip",
                "route",
                "get",
                endpoint_host,
            ]
        )

        endpoint_route_ok = (
            route_result.returncode == 0
            and f"dev {self._wan_interface}" in route_result.stdout
        )

        if not interface_up:
            reason = "interface_down"
        elif not expected_endpoint:
            reason = "endpoint_mismatch"
        elif not endpoint_route_ok:
            reason = "endpoint_route_not_via_wan"
        elif peer.latest_handshake is None:
            reason = "no_handshake"
        elif peer.rx_bytes <= 0:
            reason = "no_rx"
        elif peer.tx_bytes <= 0:
            reason = "no_tx"
        else:
            reason = None

        return AmneziaWGRuntimeHealth(
            interface_exists=True,
            interface_up=interface_up,
            expected_peer_found=True,
            expected_endpoint=expected_endpoint,
            listen_port=listen_port,
            latest_handshake=peer.latest_handshake,
            rx_bytes=peer.rx_bytes,
            tx_bytes=peer.tx_bytes,
            endpoint_route_ok=endpoint_route_ok,
            healthy=reason is None,
            reason=reason,
            checked_at=checked_at,
        )

    @staticmethod
    def _is_interface_up(output: str) -> bool:
        first_line = output.splitlines()[0] if output else ""

        if "<" not in first_line or ">" not in first_line:
            return False

        flags = first_line.split("<", 1)[1].split(">", 1)[0]

        return "UP" in {flag.strip() for flag in flags.split(",")}

    @dataclass(frozen=True, slots=True)
    class _PeerState:
        endpoint: str | None
        latest_handshake: datetime | None
        rx_bytes: int
        tx_bytes: int

    @classmethod
    def _parse_dump(
        cls,
        output: str,
    ) -> tuple[int, dict[str, _PeerState]]:
        lines = [line for line in output.splitlines() if line.strip()]

        if not lines:
            raise ValueError("AmneziaWG dump is empty")

        interface_fields = lines[0].split()

        if len(interface_fields) < 3:
            raise ValueError("Invalid AmneziaWG interface dump")

        try:
            listen_port = int(interface_fields[2])
        except ValueError as exc:
            raise ValueError("Invalid AmneziaWG listen port") from exc

        peers: dict[
            str,
            SSHAmneziaWGRuntimeHealth._PeerState,
        ] = {}

        for line in lines[1:]:
            fields = line.split()

            if len(fields) != 8:
                raise ValueError("Invalid AmneziaWG peer dump")

            public_key = fields[0]

            endpoint = None if fields[2] == "(none)" else fields[2]

            try:
                handshake_timestamp = int(fields[4])
                rx_bytes = int(fields[5])
                tx_bytes = int(fields[6])
            except ValueError as exc:
                raise ValueError("Invalid AmneziaWG peer metrics") from exc

            latest_handshake = (
                datetime.fromtimestamp(
                    handshake_timestamp,
                    tz=timezone.utc,
                )
                if handshake_timestamp > 0
                else None
            )

            peers[public_key] = cls._PeerState(
                endpoint=endpoint,
                latest_handshake=latest_handshake,
                rx_bytes=rx_bytes,
                tx_bytes=tx_bytes,
            )

        return listen_port, peers

    @staticmethod
    def _result(
        *,
        checked_at: datetime,
        interface_up: bool,
        listen_port: int | None,
        reason: str,
    ) -> AmneziaWGRuntimeHealth:
        return AmneziaWGRuntimeHealth(
            interface_exists=True,
            interface_up=interface_up,
            expected_peer_found=False,
            expected_endpoint=False,
            listen_port=listen_port,
            latest_handshake=None,
            rx_bytes=0,
            tx_bytes=0,
            endpoint_route_ok=False,
            healthy=False,
            reason=reason,
            checked_at=checked_at,
        )

    @staticmethod
    def _failed(
        checked_at: datetime,
        reason: str,
        *,
        interface_exists: bool = False,
        interface_up: bool = False,
    ) -> AmneziaWGRuntimeHealth:
        return AmneziaWGRuntimeHealth(
            interface_exists=interface_exists,
            interface_up=interface_up,
            expected_peer_found=False,
            expected_endpoint=False,
            listen_port=None,
            latest_handshake=None,
            rx_bytes=0,
            tx_bytes=0,
            endpoint_route_ok=False,
            healthy=False,
            reason=reason,
            checked_at=checked_at,
        )
