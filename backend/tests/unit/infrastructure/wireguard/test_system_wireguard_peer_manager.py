from ipaddress import IPv4Address
from unittest.mock import Mock

from app.infrastructure.executor import CommandExecutor
from app.infrastructure.wireguard.peer_manager import (
    SystemWireGuardPeerManager,
)


def test_remove_peer_executes_wg_command() -> None:
    executor = Mock(spec=CommandExecutor)

    manager = SystemWireGuardPeerManager(
        executor=executor,
        interface_name="wg0",
    )

    manager.remove_peer("PUBLIC_KEY")

    executor.run.assert_called_once_with(
        [
            "wg",
            "set",
            "wg0",
            "peer",
            "PUBLIC_KEY",
            "remove",
        ]
    )


def test_add_peer_executes_wg_command() -> None:
    executor = Mock(spec=CommandExecutor)

    manager = SystemWireGuardPeerManager(
        executor=executor,
        interface_name="wg0",
    )

    manager.add_peer(
        public_key="PUBLIC_KEY",
        address=IPv4Address("10.8.0.2"),
    )

    executor.run.assert_called_once_with(
        [
            "wg",
            "set",
            "wg0",
            "peer",
            "PUBLIC_KEY",
            "allowed-ips",
            "10.8.0.2/32",
        ]
    )
