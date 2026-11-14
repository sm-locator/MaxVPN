from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from backend.models.amneziawg_config import (
    AmneziaWGConfig,
    AmneziaWGInterface,
)
from backend.ports.amneziawg_config_persistence import AmneziaWGConfigPersistence
from backend.ports.amneziawg_config_source import AmneziaWGConfigSource
from backend.ports.amneziawg_runtime_config_source import (
    AmneziaWGRuntimeConfigSource,
)
from backend.ports.amneziawg_runtime_profile_source import (
    AmneziaWGRuntimeProfileSource,
)
from backend.services.amneziawg_config_parser import (
    AmneziaWGConfigParser,
)
from backend.services.amneziawg_config_renderer import (
    AmneziaWGConfigRenderer,
)
from backend.services.amneziawg_runtime_manager import (
    AmneziaWGRuntimeManager,
    AmneziaWGRuntimeManagerResult,
)
from backend.services.vpn_config_cipher import VPNConfigCipher

from app.models.vpn_profile import VpnProfile
from app.repositories.vpn_profile import VpnProfileRepository


@dataclass(frozen=True, slots=True)
class VpnProfileValidationResult:
    valid: bool
    interface_address: str | None
    endpoint: str | None
    allowed_ips: tuple[str, ...]
    has_private_key: bool
    has_preshared_key: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class VpnProfileRead:
    id: int
    name: str
    enabled: bool
    has_private_key: bool
    has_preshared_key: bool


class VpnProfileService:
    """
    Application service for persisted AmneziaWG VPN profiles.

    Plaintext provider configuration is decrypted only inside this
    service and is never exposed through the read model.
    """

    def __init__(
        self,
        repository: VpnProfileRepository,
        cipher: VPNConfigCipher,
        parser: AmneziaWGConfigParser | None = None,
        runtime_manager_factory: (
            Callable[
                [AmneziaWGConfig],
                AmneziaWGRuntimeManager,
            ]
            | None
        ) = None,
        config_source: AmneziaWGConfigSource | None = None,
        runtime_profile_source: AmneziaWGRuntimeProfileSource | None = None,
        runtime_config_source: AmneziaWGRuntimeConfigSource | None = None,
        persistent_config_writer: AmneziaWGConfigPersistence | None = None,
        renderer: AmneziaWGConfigRenderer | None = None,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._parser = parser or AmneziaWGConfigParser()
        self._runtime_manager_factory = runtime_manager_factory
        self._config_source = config_source
        self._runtime_profile_source = runtime_profile_source
        self._runtime_config_source = runtime_config_source
        self._persistent_config_writer = persistent_config_writer
        self._renderer = renderer or AmneziaWGConfigRenderer()

    def get(self, user_id: int) -> VpnProfileRead | None:
        profile = self._repository.get_by_user(user_id)

        if profile is None:
            return None

        config = self._decrypt_and_parse(profile)

        return VpnProfileRead(
            id=profile.id,
            name=profile.name,
            enabled=profile.enabled,
            has_private_key=bool(config.interface.private_key),
            has_preshared_key=bool(config.peer.preshared_key),
        )

    def get_config(
        self,
        user_id: int,
    ) -> AmneziaWGConfig | None:
        profile = self._repository.get_by_user(user_id)

        if profile is None:
            return None

        return self._decrypt_and_parse(profile)

    def update_config(
        self,
        user_id: int,
        config: AmneziaWGConfig,
        name: str,
        enabled: bool,
    ) -> VpnProfile:
        if not name.strip():
            raise ValueError("profile name must not be empty")

        provider_config = self._renderer.render_full(config)

        # Reuse the existing validation/encryption/upsert path.
        return self.save(
            user_id=user_id,
            name=name,
            provider_config=provider_config,
            enabled=enabled,
        )

    def save(
        self,
        user_id: int,
        name: str,
        provider_config: str,
        enabled: bool = True,
    ) -> VpnProfile:
        if not name.strip():
            raise ValueError("profile name must not be empty")

        self._parser.parse(provider_config)

        encrypted = self._cipher.encrypt(provider_config)

        existing = self._repository.get_by_user(user_id)

        if existing is None:
            return self._repository.create_for_user(
                user_id=user_id,
                name=name.strip(),
                encrypted_provider_config=encrypted,
                enabled=enabled,
            )

        existing.name = name.strip()
        existing.encrypted_provider_config = encrypted
        existing.enabled = enabled

        return self._repository.update(existing)

    def import_current_runtime(
        self,
        user_id: int,
        name: str = "Current Brume VPN",
        enabled: bool = True,
    ) -> VpnProfile:
        if self._runtime_profile_source is None:
            raise RuntimeError(
                "AmneziaWG runtime profile source is required for runtime import"
            )

        if not name.strip():
            raise ValueError("profile name must not be empty")

        config = self._runtime_profile_source.read()
        provider_config = self._renderer.render_full(config)

        # Reuse the existing validation/encryption/upsert path.
        return self.save(
            user_id=user_id,
            name=name,
            provider_config=provider_config,
            enabled=enabled,
        )

    def validate(
        self,
        provider_config: str,
    ) -> VpnProfileValidationResult:
        try:
            config = self._parser.parse(provider_config)
        except ValueError as exc:
            return VpnProfileValidationResult(
                valid=False,
                interface_address=None,
                endpoint=None,
                allowed_ips=(),
                has_private_key=False,
                has_preshared_key=False,
                reason=str(exc),
            )

        return self._validation_result(config)

    @staticmethod
    def _config_fingerprints(
        config: AmneziaWGConfig,
        *,
        include_dns: bool,
    ) -> tuple[tuple[object, ...], tuple[object, ...]]:
        interface = config.interface
        peer = config.peer

        interface_fingerprint = (
            interface.private_key,
            interface.address,
            interface.mtu,
            interface.dns if include_dns else None,
            interface.jc,
            interface.jmin,
            interface.jmax,
            interface.s1,
            interface.s2,
            interface.s3 if interface.s3 is not None else 0,
            interface.s4 if interface.s4 is not None else 0,
            interface.h1,
            interface.h2,
            interface.h3,
            interface.h4,
            interface.i1,
            interface.i2,
            interface.i3,
            interface.i4,
            interface.i5,
        )
        peer_fingerprint = (
            peer.public_key,
            peer.preshared_key,
            tuple(peer.allowed_ips),
            peer.endpoint,
            peer.persistent_keepalive,
        )
        return interface_fingerprint, peer_fingerprint

    @staticmethod
    def _configs_equal(
        desired: AmneziaWGConfig,
        actual: AmneziaWGConfig,
    ) -> bool:
        desired_interface, desired_peer = VpnProfileService._config_fingerprints(
            desired,
            include_dns=False,
        )
        actual_interface, actual_peer = VpnProfileService._config_fingerprints(
            actual,
            include_dns=False,
        )
        return desired_interface == actual_interface and desired_peer == actual_peer

    @staticmethod
    def _persistent_configs_equal(
        desired: AmneziaWGConfig,
        actual: AmneziaWGConfig,
    ) -> bool:
        desired_interface, desired_peer = VpnProfileService._config_fingerprints(
            desired,
            include_dns=True,
        )
        actual_interface, actual_peer = VpnProfileService._config_fingerprints(
            actual,
            include_dns=True,
        )
        return desired_interface == actual_interface and desired_peer == actual_peer

    @staticmethod
    def _merge_persistent_awg_fields(
        desired: AmneziaWGConfig,
        persistent: AmneziaWGConfig | None,
    ) -> AmneziaWGConfig:
        """Preserve provider AWG parameters omitted by the stored profile."""
        if persistent is None:
            return desired

        desired_interface = desired.interface
        persistent_interface = persistent.interface
        merged_interface = AmneziaWGInterface(
            private_key=desired_interface.private_key,
            address=desired_interface.address,
            mtu=desired_interface.mtu,
            dns=desired_interface.dns,
            jc=(
                desired_interface.jc
                if desired_interface.jc is not None
                else persistent_interface.jc
            ),
            jmin=(
                desired_interface.jmin
                if desired_interface.jmin is not None
                else persistent_interface.jmin
            ),
            jmax=(
                desired_interface.jmax
                if desired_interface.jmax is not None
                else persistent_interface.jmax
            ),
            s1=(
                desired_interface.s1
                if desired_interface.s1 is not None
                else persistent_interface.s1
            ),
            s2=(
                desired_interface.s2
                if desired_interface.s2 is not None
                else persistent_interface.s2
            ),
            s3=(
                desired_interface.s3
                if desired_interface.s3 is not None
                else persistent_interface.s3
            ),
            s4=(
                desired_interface.s4
                if desired_interface.s4 is not None
                else persistent_interface.s4
            ),
            h1=(
                desired_interface.h1
                if desired_interface.h1 is not None
                else persistent_interface.h1
            ),
            h2=(
                desired_interface.h2
                if desired_interface.h2 is not None
                else persistent_interface.h2
            ),
            h3=(
                desired_interface.h3
                if desired_interface.h3 is not None
                else persistent_interface.h3
            ),
            h4=(
                desired_interface.h4
                if desired_interface.h4 is not None
                else persistent_interface.h4
            ),
            i1=(
                desired_interface.i1
                if desired_interface.i1 is not None
                else persistent_interface.i1
            ),
            i2=(
                desired_interface.i2
                if desired_interface.i2 is not None
                else persistent_interface.i2
            ),
            i3=(
                desired_interface.i3
                if desired_interface.i3 is not None
                else persistent_interface.i3
            ),
            i4=(
                desired_interface.i4
                if desired_interface.i4 is not None
                else persistent_interface.i4
            ),
            i5=(
                desired_interface.i5
                if desired_interface.i5 is not None
                else persistent_interface.i5
            ),
        )
        return replace(desired, interface=merged_interface)

    def preflight_apply(
        self,
        user_id: int,
        interface: str = "WireGuard",
    ) -> bool:
        if self._runtime_config_source is None:
            raise RuntimeError(
                "AmneziaWG runtime config source is required for apply preflight"
            )

        profile = self._repository.get_by_user(user_id)

        if profile is None:
            raise LookupError("vpn_profile_not_found")

        if not profile.enabled:
            raise ValueError("vpn_profile_disabled")

        saved_config = self._decrypt_and_parse(profile)

        persistent_config = None
        persistent_in_sync = True
        effective_config = saved_config
        if self._config_source is not None:
            persistent_config = self._config_source.read()
            effective_config = self._merge_persistent_awg_fields(
                saved_config,
                persistent_config,
            )
            persistent_in_sync = self._persistent_configs_equal(
                effective_config,
                persistent_config,
            )

        if self._runtime_profile_source is not None:
            try:
                actual_config = self._runtime_profile_source.read(interface)
            except RuntimeError as exc:
                if str(exc) != "awg_showconf_failed":
                    raise
                return False

            return persistent_in_sync and self._configs_equal(
                effective_config,
                actual_config,
            )

        desired_runtime = self._renderer.render_awg_runtime(effective_config)
        actual_runtime = self._runtime_config_source.read(interface)

        return persistent_in_sync and desired_runtime == actual_runtime

    def apply(
        self,
        user_id: int,
        interface: str = "WireGuard",
        runtime_path: str = "/tmp/maxvpn-awg-runtime.conf",
    ) -> AmneziaWGRuntimeManagerResult:
        if self._runtime_manager_factory is None:
            raise RuntimeError(
                "AmneziaWGRuntimeManager factory is required for apply()"
            )

        profile = self._repository.get_by_user(user_id)

        if profile is None:
            raise LookupError("vpn_profile_not_found")

        if not profile.enabled:
            raise ValueError("vpn_profile_disabled")

        config = self._decrypt_and_parse(profile)

        effective_config = config
        persistent_config = None
        persistent_changed = False
        if self._config_source is not None:
            persistent_config = self._config_source.read()
            effective_config = self._merge_persistent_awg_fields(
                config,
                persistent_config,
            )
            persistent_changed = not self._persistent_configs_equal(
                effective_config,
                persistent_config,
            )

        actual_config = None
        runtime_in_sync = False
        if self._runtime_profile_source is not None:
            try:
                actual_config = self._runtime_profile_source.read(interface)
            except RuntimeError as exc:
                if str(exc) != "awg_showconf_failed":
                    raise
            else:
                runtime_in_sync = self._configs_equal(effective_config, actual_config)
        elif self._runtime_config_source is not None:
            desired_runtime = self._renderer.render_awg_runtime(effective_config)
            actual_runtime = self._runtime_config_source.read(interface)
            runtime_in_sync = desired_runtime == actual_runtime

        if not persistent_changed and runtime_in_sync:
            return AmneziaWGRuntimeManagerResult(
                applied=False,
                verified=True,
                rolled_back=False,
                rollback_verified=False,
                health_failed=False,
                reason=None,
                no_change=True,
            )

        if persistent_changed:
            if self._persistent_config_writer is None or self._config_source is None:
                raise RuntimeError(
                    "AmneziaWG persistent configuration writer is required"
                )

            try:
                self._persistent_config_writer.persist(effective_config)
            except Exception as exc:
                return AmneziaWGRuntimeManagerResult(
                    applied=False,
                    verified=False,
                    rolled_back=False,
                    rollback_verified=False,
                    health_failed=False,
                    reason=f"persistent_config_sync_failed: {exc}",
                    no_change=False,
                )

            try:
                persisted_config = self._config_source.read()
                if not self._persistent_configs_equal(
                    effective_config,
                    persisted_config,
                ):
                    raise RuntimeError("persistent_configuration_verification_failed")
            except Exception as exc:
                self._restore_persistent_config(persistent_config, exc)
                return AmneziaWGRuntimeManagerResult(
                    applied=False,
                    verified=False,
                    rolled_back=False,
                    rollback_verified=False,
                    health_failed=False,
                    reason=f"persistent_config_sync_failed: {exc}",
                    no_change=False,
                )

        if runtime_in_sync:
            return AmneziaWGRuntimeManagerResult(
                applied=persistent_changed,
                verified=True,
                rolled_back=False,
                rollback_verified=False,
                health_failed=False,
                reason=None,
                no_change=False,
            )

        runtime_manager = self._runtime_manager_factory(effective_config)

        try:
            result = runtime_manager.apply(
                config=effective_config,
                interface=interface,
                runtime_path=runtime_path,
            )
        except Exception as exc:
            if persistent_changed:
                self._restore_persistent_config(persistent_config, exc)
            raise

        if persistent_changed and not result.verified:
            self._restore_persistent_config(
                persistent_config,
                RuntimeError(result.reason or "runtime_apply_not_verified"),
            )
            return result

        if persistent_changed:
            return AmneziaWGRuntimeManagerResult(
                applied=True,
                verified=result.verified,
                rolled_back=result.rolled_back,
                rollback_verified=result.rollback_verified,
                health_failed=result.health_failed,
                reason=result.reason,
                no_change=False,
            )

        return result

    def _restore_persistent_config(
        self,
        snapshot: AmneziaWGConfig | None,
        original_error: Exception,
    ) -> None:
        if snapshot is None or self._persistent_config_writer is None:
            return

        try:
            self._persistent_config_writer.persist(snapshot)
            if self._config_source is not None:
                restored = self._config_source.read()
                if not self._persistent_configs_equal(snapshot, restored):
                    raise RuntimeError(
                        "persistent_configuration_rollback_verification_failed"
                    )
        except Exception as rollback_exc:
            raise RuntimeError(
                f"{original_error}; persistent_config_rollback_failed: {rollback_exc}"
            ) from rollback_exc

    def _decrypt_and_parse(
        self,
        profile: VpnProfile,
    ) -> AmneziaWGConfig:
        plaintext = self._cipher.decrypt(
            profile.encrypted_provider_config,
        )

        return self._parser.parse(plaintext)

    @staticmethod
    def _validation_result(
        config: AmneziaWGConfig,
    ) -> VpnProfileValidationResult:
        return VpnProfileValidationResult(
            valid=True,
            interface_address=config.interface.address,
            endpoint=config.peer.endpoint,
            allowed_ips=config.peer.allowed_ips,
            has_private_key=bool(config.interface.private_key),
            has_preshared_key=bool(config.peer.preshared_key),
            reason=None,
        )
