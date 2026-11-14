from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.infrastructure.wireguard.ssh_amneziawg_runtime_health import (
    ExpectedAmneziaWGPeer,
    SSHAmneziaWGRuntimeHealth,
)
from backend.models.amneziawg_runtime_health import AmneziaWGRuntimeHealth
from backend.ports.remote_command_executor import RemoteCommandExecutor


class ConfigBackedAmneziaWGRuntimeHealth:
    """Load expected peer settings lazily and report configuration failures safely.

    The wrapper deliberately does not read UCI during dependency construction.
    When UCI cannot provide the expected peer, the runtime is reported as
    unhealthy; it is never marked healthy merely because the check failed.
    """

    def __init__(
        self,
        executor: RemoteCommandExecutor,
        interface_name: str,
        config_source: Any,
        wan_interface: str = "eth1",
    ) -> None:
        self._executor = executor
        self._interface_name = interface_name
        self._config_source = config_source
        self._wan_interface = wan_interface

    def check(self) -> AmneziaWGRuntimeHealth:
        try:
            config = self._config_source.read()
        except (RuntimeError, LookupError, ValueError):
            return self._configuration_unavailable()

        expected_peer = ExpectedAmneziaWGPeer(
            public_key=config.peer.public_key,
            endpoint=config.peer.endpoint,
        )
        return SSHAmneziaWGRuntimeHealth(
            executor=self._executor,
            interface_name=self._interface_name,
            expected_peer=expected_peer,
            wan_interface=self._wan_interface,
        ).check()

    def _configuration_unavailable(self) -> AmneziaWGRuntimeHealth:
        checked_at = datetime.now(timezone.utc)
        interface_exists = False
        interface_up = False

        # UCI is unavailable, but still report the interface state when the
        # remote command succeeds. If the probe itself fails, remain unhealthy.
        try:
            result = self._executor.run(
                ["ip", "link", "show", "dev", self._interface_name]
            )
            interface_exists = result.returncode == 0
            if interface_exists:
                first_line = result.stdout.splitlines()[0] if result.stdout else ""
                if "<" in first_line and ">" in first_line:
                    flags = first_line.split("<", 1)[1].split(">", 1)[0]
                    interface_up = "UP" in {flag.strip() for flag in flags.split(",")}
        except Exception:
            # A failed diagnostic command is not evidence of a healthy link.
            pass

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
            reason="awg_config_unavailable",
            checked_at=checked_at,
        )
