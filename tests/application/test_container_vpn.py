from unittest.mock import ANY, Mock, patch

from backend.application.container import (
    build_amneziawg_runtime_manager,
)
from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
    AmneziaWGPeer,
)


def make_config() -> AmneziaWGConfig:
    return AmneziaWGConfig(
        interface=AmneziaWGInterface(
            private_key="private-key",
            address="10.100.0.2/32",
            dns="1.1.1.1",
            mtu=1420,
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=0,
            s4=0,
            h1=1,
            h2=2,
            h3=3,
            h4=4,
        ),
        peer=AmneziaWGPeer(
            public_key="public-key",
            preshared_key="preshared-key",
            allowed_ips=("0.0.0.0/0",),
            endpoint="109.172.55.99:51820",
            persistent_keepalive=25,
        ),
    )


@patch("backend.application.container.get_settings")
@patch("backend.application.container.SSHRemoteCommandExecutor")
def test_build_runtime_manager_uses_config_peer(
    executor_cls: Mock,
    settings_fn: Mock,
) -> None:
    settings = Mock(
        ssh_host="192.168.8.1",
        ssh_username="root",
        ssh_private_key_path="/tmp/key",
        ssh_port=22,
        amneziawg_interface="WireGuard",
    )
    settings_fn.return_value = settings

    executor = Mock()
    executor_cls.return_value = executor

    with (
        patch(
            "backend.application.container.SSHAmneziaWGRuntimeHealth",
        ) as health_cls,
        patch(
            "backend.application.container.AmneziaWGRuntimeApplier",
        ) as applier_cls,
        patch(
            "backend.application.container.SSHAmneziaWGRuntimeSnapshot",
        ) as snapshot_cls,
        patch(
            "backend.application.container.AmneziaWGRuntimeManager",
        ) as manager_cls,
    ):
        config = make_config()

        result = build_amneziawg_runtime_manager(config)

    assert result is manager_cls.return_value

    executor_cls.assert_called_once_with(
        host="192.168.8.1",
        username="root",
        private_key_path="/tmp/key",
        port=22,
    )

    health_cls.assert_called_once()
    health_kwargs = health_cls.call_args.kwargs

    assert health_kwargs["executor"] is executor
    assert health_kwargs["interface_name"] == "WireGuard"

    expected_peer = health_kwargs["expected_peer"]
    assert expected_peer.public_key == "public-key"
    assert expected_peer.endpoint == "109.172.55.99:51820"

    applier_cls.assert_called_once_with(
        command_executor=executor,
    )
    snapshot_cls.assert_called_once_with(
        executor=executor,
    )

    manager_cls.assert_called_once_with(
        applier=applier_cls.return_value,
        snapshot=snapshot_cls.return_value,
        health_checker=health_cls.return_value,
        lifecycle=ANY,
    )


def test_build_vpn_profile_service_uses_openwrt_config_source() -> None:
    from unittest.mock import patch

    from backend.application.container import (
        build_vpn_profile_service,
    )

    class Settings:
        ssh_host = "192.168.8.1"
        ssh_username = "root"
        ssh_private_key_path = "/tmp/key"
        ssh_port = 22
        amneziawg_interface = "WireGuard"
        vpn_config_encryption_key = (
            "2T6hQ0VJk4M0oW8n5L6V4h8z3K2y1X0wQ9m8N7b6C5x4Z3a2S1d0F9g8H7j6K5l4"
        )

    session = Mock()
    executor = Mock()

    with (
        patch(
            "backend.application.container.get_settings",
            return_value=Settings(),
        ),
        patch(
            "backend.application.container.SSHRemoteCommandExecutor",
            return_value=executor,
        ) as executor_cls,
        patch(
            "backend.application.container.OpenWrtAmneziaWGConfigSource",
        ) as source_cls,
        patch(
            "backend.application.container.VpnProfileService",
        ) as service_cls,
        patch(
            "backend.application.container.VpnProfileRepository",
        ) as repository_cls,
        patch(
            "backend.application.container.VPNConfigCipher",
        ) as cipher_cls,
        patch(
            "backend.application.container.build_amneziawg_runtime_manager",
        ) as runtime_factory,
        patch(
            "backend.application.container.OpenWrtAmneziaWGConfigPersistence",
        ) as persistent_writer_cls,
    ):
        result = build_vpn_profile_service(session)

    assert result is service_cls.return_value

    executor_cls.assert_called_once_with(
        host="192.168.8.1",
        username="root",
        private_key_path="/tmp/key",
        port=22,
    )

    source_cls.assert_called_once_with(
        executor=executor,
        interface="WireGuard",
    )

    repository_cls.assert_called_once_with(session)
    cipher_cls.assert_called_once_with(Settings.vpn_config_encryption_key)

    service_cls.assert_called_once_with(
        repository=repository_cls.return_value,
        cipher=cipher_cls.return_value,
        runtime_manager_factory=runtime_factory,
        config_source=source_cls.return_value,
        runtime_profile_source=ANY,
        runtime_config_source=ANY,
        persistent_config_writer=persistent_writer_cls.return_value,
    )
