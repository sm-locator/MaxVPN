from backend.infrastructure.wireguard.dry_run_peer_manager import (
    DryRunWireGuardPeerManager,
)


def test_add_peer_does_not_touch_system():
    manager = DryRunWireGuardPeerManager()

    manager.add_peer(
        public_key="client-public-key",
        address="10.100.0.2",
    )

    assert manager.added_peers == [
        ("client-public-key", "10.100.0.2"),
    ]


def test_remove_peer_does_not_touch_system():
    manager = DryRunWireGuardPeerManager()

    manager.remove_peer(
        public_key="client-public-key",
    )

    assert manager.removed_peers == [
        "client-public-key",
    ]
