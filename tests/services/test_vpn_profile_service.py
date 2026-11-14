from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.models.vpn_profile import VpnProfile
from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
    AmneziaWGPeer,
)
from backend.services.amneziawg_runtime_manager import (
    AmneziaWGRuntimeManagerResult,
)
from backend.services.vpn_profile_service import (
    VpnProfileService,
)

PROVIDER_CONFIG = """[Interface]
PrivateKey = private-key
Address = 10.100.0.2/32
DNS = 1.1.1.1
MTU = 1420
Jc = 5
Jmin = 2
Jmax = 9
S1 = 0
S2 = 0
S3 = 0
S4 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4

[Peer]
PublicKey = public-key
PresharedKey = preshared-key
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
Endpoint = 109.172.55.99:51820
"""


def make_config(
    endpoint: str = "109.172.55.99:51820",
    address: str = "10.100.0.2/32",
) -> AmneziaWGConfig:
    return AmneziaWGConfig(
        interface=AmneziaWGInterface(
            private_key="private-key",
            address=address,
            dns="1.1.1.1",
            mtu=1380,
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=None,
            s4=None,
            h1="1",
            h2="2",
            h3="3",
            h4="4",
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=AmneziaWGPeer(
            public_key="public-key",
            preshared_key="preshared-key",
            allowed_ips=("0.0.0.0/0", "::/0"),
            endpoint=endpoint,
            persistent_keepalive=25,
        ),
    )


def make_service():
    repository = Mock()
    cipher = Mock()
    parser = Mock()
    runtime_manager = Mock()
    runtime_manager_factory = Mock(return_value=runtime_manager)

    return (
        VpnProfileService(
            repository=repository,
            cipher=cipher,
            parser=parser,
            runtime_manager_factory=runtime_manager_factory,
        ),
        repository,
        cipher,
        parser,
        runtime_manager_factory,
        runtime_manager,
    )


def make_import_service():
    repository = Mock()
    cipher = Mock()
    parser = Mock()
    runtime_manager = Mock()
    runtime_manager_factory = Mock(return_value=runtime_manager)
    config_source = Mock()
    runtime_profile_source = Mock()
    runtime_config_source = Mock()
    persistent_config_writer = Mock()
    renderer = Mock()

    service = VpnProfileService(
        repository=repository,
        cipher=cipher,
        parser=parser,
        runtime_manager_factory=runtime_manager_factory,
        config_source=config_source,
        runtime_profile_source=runtime_profile_source,
        runtime_config_source=runtime_config_source,
        persistent_config_writer=persistent_config_writer,
        renderer=renderer,
    )
    return (
        service,
        repository,
        cipher,
        parser,
        runtime_manager,
        config_source,
        runtime_profile_source,
        runtime_config_source,
        persistent_config_writer,
        renderer,
    )


def test_merge_persistent_awg_fields_preserves_provider_parameters() -> None:
    desired = make_config(endpoint="109.172.55.200:51820")
    desired = replace(
        desired,
        interface=replace(
            desired.interface,
            jc=None,
            jmin=None,
            jmax=None,
            s1=None,
            s2=None,
            s3=None,
            s4=None,
            h1=None,
            h2=None,
            h3=None,
            h4=None,
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
    )
    persistent = make_config(endpoint="109.172.55.99:51820")

    merged = VpnProfileService._merge_persistent_awg_fields(
        desired,
        persistent,
    )

    assert merged.peer.endpoint == "109.172.55.200:51820"
    assert merged.interface.jc == persistent.interface.jc
    assert merged.interface.jmin == persistent.interface.jmin
    assert merged.interface.jmax == persistent.interface.jmax
    assert merged.interface.s1 == persistent.interface.s1
    assert merged.interface.s2 == persistent.interface.s2
    assert merged.interface.s3 == persistent.interface.s3
    assert merged.interface.s4 == persistent.interface.s4
    assert merged.interface.h1 == persistent.interface.h1
    assert merged.interface.h2 == persistent.interface.h2
    assert merged.interface.h3 == persistent.interface.h3
    assert merged.interface.h4 == persistent.interface.h4
    assert merged.interface.i1 == persistent.interface.i1
    assert merged.interface.i2 == persistent.interface.i2
    assert merged.interface.i3 == persistent.interface.i3
    assert merged.interface.i4 == persistent.interface.i4
    assert merged.interface.i5 == persistent.interface.i5


def test_save_creates_new_profile_with_encrypted_config() -> None:
    service, repository, cipher, parser, _, _ = make_service()

    parsed = Mock()
    parser.parse.return_value = parsed
    cipher.encrypt.return_value = "encrypted-config"
    repository.get_by_user.return_value = None

    created = Mock()
    repository.create_for_user.return_value = created

    result = service.save(
        user_id=42,
        name="Primary VPN",
        provider_config=PROVIDER_CONFIG,
    )

    assert result is created

    parser.parse.assert_called_once_with(PROVIDER_CONFIG)
    cipher.encrypt.assert_called_once_with(PROVIDER_CONFIG)
    repository.create_for_user.assert_called_once_with(
        user_id=42,
        name="Primary VPN",
        encrypted_provider_config="encrypted-config",
        enabled=True,
    )


def test_save_updates_existing_profile() -> None:
    service, repository, cipher, parser, _, _ = make_service()

    parsed = Mock()
    parser.parse.return_value = parsed
    cipher.encrypt.return_value = "new-encrypted"

    existing = VpnProfile(
        user_id=42,
        name="Old",
        enabled=False,
        encrypted_provider_config="old-encrypted",
    )
    repository.get_by_user.return_value = existing

    updated = Mock()
    repository.update.return_value = updated

    result = service.save(
        user_id=42,
        name="New Name",
        provider_config=PROVIDER_CONFIG,
        enabled=True,
    )

    assert result is updated
    assert existing.name == "New Name"
    assert existing.enabled is True
    assert existing.encrypted_provider_config == "new-encrypted"

    repository.update.assert_called_once_with(existing)


def test_save_rejects_empty_name() -> None:
    service, repository, cipher, parser, _, _ = make_service()

    with pytest.raises(
        ValueError,
        match="profile name must not be empty",
    ):
        service.save(
            user_id=42,
            name="   ",
            provider_config=PROVIDER_CONFIG,
        )

    parser.parse.assert_not_called()
    cipher.encrypt.assert_not_called()
    repository.get_by_user.assert_not_called()


def test_validate_returns_sanitized_result() -> None:
    service, _, _, parser, _, _ = make_service()

    interface = Mock(
        address="10.100.0.2/32",
        private_key="private-key",
    )
    peer = Mock(
        endpoint="109.172.55.99:51820",
        allowed_ips=("0.0.0.0/0",),
        preshared_key="preshared-key",
    )

    config = Mock(
        interface=interface,
        peer=peer,
    )

    parser.parse.return_value = config

    result = service.validate(PROVIDER_CONFIG)

    assert result.valid is True
    assert result.interface_address == "10.100.0.2/32"
    assert result.endpoint == "109.172.55.99:51820"
    assert result.allowed_ips == ("0.0.0.0/0",)
    assert result.has_private_key is True
    assert result.has_preshared_key is True
    assert result.reason is None


def test_validate_returns_parser_error_without_raising() -> None:
    service, _, _, parser, _, _ = make_service()

    parser.parse.side_effect = ValueError("invalid config")

    result = service.validate("broken")

    assert result.valid is False
    assert result.interface_address is None
    assert result.endpoint is None
    assert result.allowed_ips == ()
    assert result.has_private_key is False
    assert result.has_preshared_key is False
    assert result.reason == "invalid config"


def test_get_decrypts_and_returns_only_sanitized_metadata() -> None:
    service, repository, cipher, parser, _, _ = make_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Primary VPN",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG

    interface = Mock(
        private_key="private-key",
    )
    peer = Mock(
        preshared_key="preshared-key",
    )

    parser.parse.return_value = Mock(
        interface=interface,
        peer=peer,
    )

    result = service.get(42)

    assert result is not None
    assert result.id == 7
    assert result.name == "Primary VPN"
    assert result.enabled is True
    assert result.has_private_key is True
    assert result.has_preshared_key is True

    assert not hasattr(result, "private_key")
    assert not hasattr(result, "preshared_key")

    cipher.decrypt.assert_called_once_with("encrypted-value")
    parser.parse.assert_called_once_with(PROVIDER_CONFIG)


def test_get_returns_none_when_profile_missing() -> None:
    service, repository, cipher, parser, _, _ = make_service()

    repository.get_by_user.return_value = None

    assert service.get(42) is None

    cipher.decrypt.assert_not_called()
    parser.parse.assert_not_called()


def test_apply_decrypts_parses_and_calls_runtime_manager() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        runtime_manager_factory,
        runtime_manager,
    ) = make_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Primary VPN",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG

    parsed = Mock()
    parser.parse.return_value = parsed

    expected = AmneziaWGRuntimeManagerResult(
        applied=True,
        verified=True,
        rolled_back=False,
        rollback_verified=False,
        health_failed=False,
        reason=None,
    )
    runtime_manager.apply.return_value = expected

    result = service.apply(
        user_id=42,
        interface="WireGuard",
        runtime_path="/tmp/runtime.conf",
    )

    assert result is expected

    cipher.decrypt.assert_called_once_with("encrypted-value")
    parser.parse.assert_called_once_with(PROVIDER_CONFIG)
    runtime_manager_factory.assert_called_once_with(parsed)
    runtime_manager.apply.assert_called_once_with(
        config=parsed,
        interface="WireGuard",
        runtime_path="/tmp/runtime.conf",
    )


def test_apply_rejects_missing_profile() -> None:
    service, repository, _, _, _, runtime_manager = make_service()

    repository.get_by_user.return_value = None

    with pytest.raises(
        LookupError,
        match="vpn_profile_not_found",
    ):
        service.apply(42)

    runtime_manager.apply.assert_not_called()


def test_apply_rejects_disabled_profile() -> None:
    service, repository, _, _, _, runtime_manager = make_service()

    repository.get_by_user.return_value = VpnProfile(
        id=7,
        user_id=42,
        name="Disabled",
        enabled=False,
        encrypted_provider_config="encrypted-value",
    )

    with pytest.raises(
        ValueError,
        match="vpn_profile_disabled",
    ):
        service.apply(42)

    runtime_manager.apply.assert_not_called()


def test_import_current_runtime_renders_encrypts_and_persists() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        runtime_manager,
        _config_source,
        runtime_profile_source,
        _runtime_config_source,
        _persistent_config_writer,
        renderer,
    ) = make_import_service()

    config = Mock(spec=AmneziaWGConfig)
    runtime_profile_source.read.return_value = config

    renderer.render_full.return_value = PROVIDER_CONFIG
    cipher.encrypt.return_value = "encrypted-current-runtime"
    repository.get_by_user.return_value = None

    created = Mock()
    repository.create_for_user.return_value = created

    result = service.import_current_runtime(
        user_id=42,
        name="Current Brume",
        enabled=True,
    )

    assert result is created

    runtime_profile_source.read.assert_called_once_with()
    renderer.render_full.assert_called_once_with(config)

    parser.parse.assert_called_once_with(PROVIDER_CONFIG)
    cipher.encrypt.assert_called_once_with(PROVIDER_CONFIG)

    repository.create_for_user.assert_called_once_with(
        user_id=42,
        name="Current Brume",
        encrypted_provider_config="encrypted-current-runtime",
        enabled=True,
    )

    runtime_manager.apply.assert_not_called()


def test_import_current_runtime_requires_runtime_profile_source() -> None:
    (
        _service,
        repository,
        cipher,
        parser,
        runtime_manager,
        config_source,
        _runtime_profile_source,
        _runtime_config_source,
        _persistent_config_writer,
        renderer,
    ) = make_import_service()

    runtime_manager_factory = Mock(return_value=runtime_manager)

    service = VpnProfileService(
        repository=repository,
        cipher=cipher,
        parser=parser,
        runtime_manager_factory=runtime_manager_factory,
        config_source=config_source,
        renderer=renderer,
    )

    with pytest.raises(
        RuntimeError,
        match="AmneziaWG runtime profile source is required",
    ):
        service.import_current_runtime(42)

    runtime_manager.apply.assert_not_called()


def test_apply_returns_no_change_when_runtime_matches_profile() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    config = AmneziaWGConfig(
        interface=Mock(
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
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=Mock(
            public_key="public-key",
            preshared_key="preshared-key",
            allowed_ips=("0.0.0.0/0",),
            endpoint="109.172.55.99:51820",
            persistent_keepalive=25,
        ),
    )

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = config
    config_source.read.return_value = config
    runtime_profile_source.read.return_value = config

    result = service.apply(
        user_id=42,
        interface="WireGuard",
        runtime_path="/tmp/runtime.conf",
    )

    assert result.applied is False
    assert result.verified is True
    assert result.no_change is True
    assert result.rolled_back is False
    assert result.rollback_verified is False
    assert result.health_failed is False
    assert result.reason is None

    runtime_profile_source.read.assert_called_once_with("WireGuard")
    runtime_manager.apply.assert_not_called()


def test_preflight_apply_returns_true_when_runtime_matches_profile() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        _runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        _persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    config = AmneziaWGConfig(
        interface=Mock(
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
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=Mock(
            public_key="public-key",
            preshared_key="preshared-key",
            allowed_ips=("0.0.0.0/0",),
            endpoint="109.172.55.99:51820",
            persistent_keepalive=25,
        ),
    )

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = config
    config_source.read.return_value = config
    runtime_profile_source.read.return_value = config

    assert service.preflight_apply(42) is True

    runtime_profile_source.read.assert_called_once_with("WireGuard")


def test_preflight_apply_returns_false_when_runtime_differs() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        _runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        _persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    saved_config = make_config(endpoint="109.172.55.200:51820")
    actual_config = make_config(endpoint="109.172.55.99:51820")

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = saved_config
    config_source.read.return_value = saved_config
    runtime_profile_source.read.return_value = actual_config

    assert service.preflight_apply(42) is False

    runtime_profile_source.read.assert_called_once_with("WireGuard")


def test_apply_uses_runtime_manager_when_runtime_differs() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        _persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    saved_config = make_config(endpoint="109.172.55.200:51820")
    actual_config = make_config(endpoint="109.172.55.99:51820")

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = saved_config
    config_source.read.return_value = saved_config
    runtime_profile_source.read.return_value = actual_config

    expected = AmneziaWGRuntimeManagerResult(
        applied=True,
        verified=True,
        rolled_back=False,
        rollback_verified=False,
        health_failed=False,
        reason=None,
    )

    runtime_manager.apply.return_value = expected

    result = service.apply(
        user_id=42,
        interface="WireGuard",
        runtime_path="/tmp/runtime.conf",
    )

    assert result is expected

    runtime_profile_source.read.assert_called_once_with("WireGuard")

    runtime_manager.apply.assert_called_once_with(
        config=saved_config,
        interface="WireGuard",
        runtime_path="/tmp/runtime.conf",
    )


def test_apply_persists_uci_when_runtime_matches_but_persistent_differs() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    desired = AmneziaWGConfig(
        interface=Mock(
            private_key="new-private",
            address="10.8.0.20/24",
            dns="1.1.1.1",
            mtu=1380,
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=None,
            s4=None,
            h1="1",
            h2="2",
            h3="3",
            h4="4",
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=Mock(
            public_key="new-public",
            preshared_key="new-preshared",
            allowed_ips=("0.0.0.0/0", "::/0"),
            endpoint="109.172.55.200:51820",
            persistent_keepalive=25,
        ),
    )
    previous = AmneziaWGConfig(
        interface=Mock(
            private_key="old-private",
            address="10.8.0.20/24",
            dns="1.1.1.1",
            mtu=1380,
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=None,
            s4=None,
            h1="1",
            h2="2",
            h3="3",
            h4="4",
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=Mock(
            public_key="old-public",
            preshared_key="old-preshared",
            allowed_ips=("0.0.0.0/0",),
            endpoint="109.172.55.99:51820",
            persistent_keepalive=25,
        ),
    )

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = desired
    config_source.read.side_effect = [previous, desired]
    runtime_profile_source.read.return_value = desired

    result = service.apply(42)

    assert result.applied is True
    assert result.verified is True
    assert result.no_change is False
    persistent_config_writer.persist.assert_called_once()
    persisted = persistent_config_writer.persist.call_args.args[0]

    assert persisted.interface.private_key == desired.interface.private_key
    assert persisted.interface.address == desired.interface.address
    assert persisted.interface.dns == desired.interface.dns
    assert persisted.interface.mtu == desired.interface.mtu
    assert persisted.interface.jc == desired.interface.jc
    assert persisted.interface.jmin == desired.interface.jmin
    assert persisted.interface.jmax == desired.interface.jmax
    assert persisted.interface.s1 == desired.interface.s1
    assert persisted.interface.s2 == desired.interface.s2
    assert persisted.interface.s3 == desired.interface.s3
    assert persisted.interface.s4 == desired.interface.s4
    assert persisted.interface.h1 == desired.interface.h1
    assert persisted.interface.h2 == desired.interface.h2
    assert persisted.interface.h3 == desired.interface.h3
    assert persisted.interface.h4 == desired.interface.h4
    assert persisted.interface.i1 == desired.interface.i1
    assert persisted.interface.i2 == desired.interface.i2
    assert persisted.interface.i3 == desired.interface.i3
    assert persisted.interface.i4 == desired.interface.i4
    assert persisted.interface.i5 == desired.interface.i5
    assert persisted.peer == desired.peer
    runtime_manager.apply.assert_not_called()


def test_preflight_apply_requires_persistent_and_runtime_sync() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        _runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )
    saved = make_config(endpoint="109.172.55.200:51820")
    persistent = make_config(endpoint="109.172.55.99:51820")

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = saved
    config_source.read.return_value = persistent
    runtime_profile_source.read.return_value = saved

    assert service.preflight_apply(42) is False


def test_apply_does_not_start_runtime_when_persistent_write_fails() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )
    desired = make_config(endpoint="109.172.55.200:51820")
    previous = make_config(endpoint="109.172.55.99:51820")

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = desired
    config_source.read.return_value = previous
    runtime_profile_source.read.return_value = previous
    persistent_config_writer.persist.side_effect = RuntimeError("permission denied")

    result = service.apply(42)

    assert result.applied is False
    assert result.verified is False
    assert result.no_change is False
    assert "persistent_config_sync_failed" in (result.reason or "")
    runtime_manager.apply.assert_not_called()


def test_apply_restores_persistent_config_when_runtime_apply_fails() -> None:
    (
        service,
        repository,
        cipher,
        parser,
        runtime_manager,
        config_source,
        runtime_profile_source,
        _runtime_config_source,
        persistent_config_writer,
        _renderer,
    ) = make_import_service()

    profile = VpnProfile(
        id=7,
        user_id=42,
        name="Current Brume",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )
    desired = make_config(endpoint="109.172.55.200:51820")
    previous = make_config(endpoint="109.172.55.99:51820")

    repository.get_by_user.return_value = profile
    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = desired
    config_source.read.side_effect = [previous, desired, previous]
    runtime_profile_source.read.return_value = previous
    runtime_manager.apply.return_value = AmneziaWGRuntimeManagerResult(
        applied=False,
        verified=False,
        rolled_back=True,
        rollback_verified=True,
        health_failed=True,
        reason="awg_health_verification_failed",
    )

    result = service.apply(42)

    assert result.health_failed is True
    assert persistent_config_writer.persist.call_count == 2
    persistent_config_writer.persist.assert_any_call(desired)
    persistent_config_writer.persist.assert_any_call(previous)


def test_update_config_preserves_secret_keys() -> None:
    service, repository, cipher, parser, _, _ = make_service()

    existing = VpnProfile(
        id=7,
        user_id=42,
        name="Current",
        enabled=True,
        encrypted_provider_config="encrypted-value",
    )

    repository.get_by_user.return_value = existing
    cipher.decrypt.return_value = PROVIDER_CONFIG

    parsed = AmneziaWGConfig(
        interface=Mock(
            private_key="existing-private",
            address="10.100.0.2/32",
            mtu=1420,
            dns="1.1.1.1",
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=0,
            s4=0,
            h1="1",
            h2="2",
            h3="3",
            h4="4",
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=Mock(
            public_key="existing-public",
            allowed_ips=("0.0.0.0/0",),
            endpoint="109.172.55.99:51820",
            persistent_keepalive=25,
            preshared_key="existing-preshared",
        ),
    )

    cipher.decrypt.return_value = PROVIDER_CONFIG
    parser.parse.return_value = parsed
    cipher.encrypt.return_value = "new-encrypted"
    repository.update.return_value = existing

    result = service.update_config(
        user_id=42,
        config=parsed,
        name="Updated",
        enabled=True,
    )

    assert result is existing
    assert existing.name == "Updated"
    assert existing.encrypted_provider_config == "new-encrypted"
    cipher.encrypt.assert_called_once()


def test_configs_equal_normalizes_runtime_defaults() -> None:
    from types import SimpleNamespace

    desired = SimpleNamespace(
        interface=SimpleNamespace(
            private_key="private",
            address="10.8.0.26/24",
            mtu=1380,
            dns="1.1.1.1",
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=None,
            s4=None,
            h1="1",
            h2="2",
            h3="3",
            h4="4",
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=SimpleNamespace(
            public_key="public",
            preshared_key="preshared",
            allowed_ips=("0.0.0.0/0", "::/0"),
            endpoint="109.172.55.99:51820",
            persistent_keepalive=25,
        ),
    )

    actual = SimpleNamespace(
        interface=SimpleNamespace(
            private_key="private",
            address="10.8.0.26/24",
            mtu=1380,
            dns=None,
            jc=5,
            jmin=2,
            jmax=9,
            s1=0,
            s2=0,
            s3=0,
            s4=0,
            h1="1",
            h2="2",
            h3="3",
            h4="4",
            i1=None,
            i2=None,
            i3=None,
            i4=None,
            i5=None,
        ),
        peer=SimpleNamespace(
            public_key="public",
            preshared_key="preshared",
            allowed_ips=("0.0.0.0/0", "::/0"),
            endpoint="109.172.55.99:51820",
            persistent_keepalive=25,
        ),
    )

    assert VpnProfileService._configs_equal(desired, actual) is True


def test_configs_equal_detects_real_runtime_difference() -> None:
    from types import SimpleNamespace

    def make_config(jc: int):
        return SimpleNamespace(
            interface=SimpleNamespace(
                private_key="private",
                address="10.8.0.26/24",
                mtu=1380,
                dns="1.1.1.1",
                jc=jc,
                jmin=2,
                jmax=9,
                s1=0,
                s2=0,
                s3=0,
                s4=0,
                h1="1",
                h2="2",
                h3="3",
                h4="4",
                i1=None,
                i2=None,
                i3=None,
                i4=None,
                i5=None,
            ),
            peer=SimpleNamespace(
                public_key="public",
                preshared_key="preshared",
                allowed_ips=("0.0.0.0/0", "::/0"),
                endpoint="109.172.55.99:51820",
                persistent_keepalive=25,
            ),
        )

    assert (
        VpnProfileService._configs_equal(
            make_config(5),
            make_config(6),
        )
        is False
    )
