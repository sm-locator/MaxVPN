from pathlib import Path
from unittest.mock import patch

from backend.infrastructure.wireguard.system_server_manager import (
    SystemWireGuardServerManager,
)


def test_interface_exists_returns_true_when_interface_exists():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 0

        assert manager.interface_exists() is True

    run.assert_called_once_with(
        [
            "ip",
            "link",
            "show",
            "dev",
            "wg0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_interface_exists_returns_false_when_interface_does_not_exist():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 1

        assert manager.interface_exists() is False


def test_ensure_interface_creates_missing_interface():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 1

        manager.ensure_interface()

    assert run.call_count == 2

    run.assert_any_call(
        [
            "ip",
            "link",
            "show",
            "dev",
            "wg0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    run.assert_any_call(
        [
            "ip",
            "link",
            "add",
            "wg0",
            "type",
            "wireguard",
        ],
        check=True,
    )


def test_ensure_interface_does_not_recreate_existing_interface():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 0

        manager.ensure_interface()

    run.assert_called_once()


def test_configure_sets_private_key_and_listen_port():
    manager = SystemWireGuardServerManager("wg0")

    private_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        with patch.object(Path, "write_text") as write_text:
            with patch.object(Path, "chmod") as chmod:
                with patch.object(Path, "unlink") as unlink:
                    manager.configure(
                        private_key=private_key,
                        listen_port=51820,
                    )

    write_text.assert_called_once_with(
        private_key,
        encoding="utf-8",
    )

    chmod.assert_called_once_with(0o600)

    unlink.assert_called_once_with(
        missing_ok=True,
    )

    run.assert_called_once_with(
        [
            "wg",
            "set",
            "wg0",
            "private-key",
            "/tmp/wg0.privatekey",
            "listen-port",
            "51820",
        ],
        check=True,
    )


def test_configure_address_replaces_interface_address():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        manager.configure_address("10.100.0.1/24")

    run.assert_called_once_with(
        [
            "ip",
            "address",
            "replace",
            "10.100.0.1/24",
            "dev",
            "wg0",
        ],
        check=True,
    )


def test_set_up_bring_interface_up():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        manager.set_up()

    run.assert_called_once_with(
        [
            "ip",
            "link",
            "set",
            "dev",
            "wg0",
            "up",
        ],
        check=True,
    )


def test_set_down_bring_interface_down():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        manager.set_down()

    run.assert_called_once_with(
        [
            "ip",
            "link",
            "set",
            "dev",
            "wg0",
            "down",
        ],
        check=True,
    )


def test_is_up_returns_true_when_interface_is_up():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = (
            "5: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1420 state UNKNOWN\n"
        )

        assert manager.is_up() is True


def test_is_up_returns_false_when_interface_is_missing():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 1
        run.return_value.stdout = ""

        assert manager.is_up() is False


def test_is_up_returns_false_when_interface_is_down():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 0
        run.return_value.stdout = "5: wg0: <POINTOPOINT,NOARP> mtu 1420 state DOWN\n"

        assert manager.is_up() is False


def test_remove_interface_deletes_existing_interface():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 0

        manager.remove_interface()

    assert run.call_count == 2

    run.assert_any_call(
        [
            "ip",
            "link",
            "show",
            "dev",
            "wg0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    run.assert_any_call(
        [
            "ip",
            "link",
            "delete",
            "dev",
            "wg0",
        ],
        check=True,
    )


def test_remove_interface_does_nothing_when_interface_is_missing():
    manager = SystemWireGuardServerManager("wg0")

    with patch(
        "backend.infrastructure.wireguard.system_server_manager.subprocess.run"
    ) as run:
        run.return_value.returncode = 1

        manager.remove_interface()

    run.assert_called_once()
