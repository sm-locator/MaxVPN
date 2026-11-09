from unittest.mock import patch

from backend.infrastructure.wireguard.system_peer_manager import (
    SystemWireGuardPeerManager,
)


def test_add_peer_builds_expected_wg_command():
    manager = SystemWireGuardPeerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_peer_manager.subprocess.run"
    ) as run:
        manager.add_peer(
            public_key="client-public-key",
            address="10.100.0.2",
        )

    run.assert_called_once_with(
        [
            "wg",
            "set",
            "wg0",
            "peer",
            "client-public-key",
            "allowed-ips",
            "10.100.0.2/32",
        ],
        check=True,
    )


def test_remove_peer_builds_expected_wg_command():
    manager = SystemWireGuardPeerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_peer_manager.subprocess.run"
    ) as run:
        manager.remove_peer(
            public_key="client-public-key",
        )

    run.assert_called_once_with(
        [
            "wg",
            "set",
            "wg0",
            "peer",
            "client-public-key",
            "remove",
        ],
        check=True,
    )


def test_custom_binary_is_used():
    manager = SystemWireGuardPeerManager(
        "wg0",
        binary="/usr/bin/wg",
    )

    with patch(
        "backend.infrastructure.wireguard.system_peer_manager.subprocess.run"
    ) as run:
        manager.add_peer(
            public_key="client-public-key",
            address="10.100.0.2",
        )

    run.assert_called_once_with(
        [
            "/usr/bin/wg",
            "set",
            "wg0",
            "peer",
            "client-public-key",
            "allowed-ips",
            "10.100.0.2/32",
        ],
        check=True,
    )
