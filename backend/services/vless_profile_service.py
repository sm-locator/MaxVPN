from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode

from backend.models.vless_config import VlessRealityConfig, VlessServerConfig
from backend.services.vless_profile_importer import VlessProfileImporter
from backend.services.vpn_config_cipher import VPNConfigCipher

from app.repositories.vless_profile import VlessProfileRepository


@dataclass(frozen=True, slots=True)
class VlessProfileRead:
    id: int
    name: str
    enabled: bool
    address: str
    port: int
    flow: str | None
    security: str
    server_name: str | None
    fingerprint: str | None
    has_uuid: bool


@dataclass(frozen=True, slots=True)
class VlessProfileValidation:
    valid: bool
    name: str | None = None
    address: str | None = None
    port: int | None = None
    flow: str | None = None
    security: str | None = None
    server_name: str | None = None
    fingerprint: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class VlessBatchImportItem:
    index: int
    status: str
    profile: VlessProfileRead | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class VlessBatchImportResult:
    limit: int
    total: int
    imported: int
    failed: int
    duplicates: int
    limit_reached: int
    items: list[VlessBatchImportItem]


class VlessProfileService:
    """Import, encrypt, persist and read up to 50 VLESS profiles per user."""

    MAX_PROFILES = 50

    def __init__(
        self,
        repository: VlessProfileRepository,
        cipher: VPNConfigCipher,
        importer: VlessProfileImporter | None = None,
        settings_repository: Any | None = None,
    ) -> None:
        self._repository = repository
        self._cipher = cipher
        self._importer = importer or VlessProfileImporter()
        self._settings_repository = settings_repository

    def save(
        self,
        user_id: int,
        source: str,
        name: str | None = None,
        enabled: bool = True,
    ) -> VlessProfileRead:
        """Append a profile; importing no longer overwrites the previous server."""
        server = self._importer.parse(source)
        profile_name = self._validate_name(name if name is not None else server.name)
        records = self._records(user_id)
        identity = self._server_identity(server)
        for record in records:
            try:
                existing_server = self._decrypt_server(record.encrypted_config)
            except ValueError:
                continue
            if self._server_identity(existing_server) == identity:
                record.name = profile_name
                record.enabled = enabled
                updated = self._repository.update(record)
                return self._to_read(updated, server)
        if len(records) >= self.MAX_PROFILES:
            raise ValueError(
                "vless_profile_limit_reached: maximum is 50 profiles per user"
            )
        return self._persist_server(user_id, server, profile_name, enabled)

    def import_many(self, user_id: int, sources: list[str]) -> VlessBatchImportResult:
        if not sources:
            raise ValueError("At least one VLESS link is required")
        if len(sources) > self.MAX_PROFILES:
            raise ValueError("A batch may contain at most 50 VLESS links")

        records = self._records(user_id)
        signatures: set[tuple[Any, ...]] = set()
        for record in records:
            try:
                signatures.add(
                    self._server_identity(self._decrypt_server(record.encrypted_config))
                )
            except ValueError:
                # Don't prevent an import because an older stored record is damaged.
                continue

        current_count = len(records)
        items: list[VlessBatchImportItem] = []
        imported = failed = duplicates = limit_reached = 0

        for index, source in enumerate(sources, start=1):
            try:
                server = self._importer.parse(source)
            except ValueError as exc:
                items.append(VlessBatchImportItem(index, "invalid", reason=str(exc)))
                failed += 1
                continue

            signature = self._server_identity(server)
            if signature in signatures:
                items.append(
                    VlessBatchImportItem(
                        index, "duplicate", reason="Этот сервер уже импортирован"
                    )
                )
                duplicates += 1
                continue

            if current_count >= self.MAX_PROFILES:
                items.append(
                    VlessBatchImportItem(
                        index,
                        "limit_reached",
                        reason="Достигнут лимит 50 профилей; удалите ненужный сервер",
                    )
                )
                limit_reached += 1
                continue

            try:
                profile_name = self._validate_name(server.name)
                saved = self._persist_server(
                    user_id, server, profile_name, enabled=True
                )
            except ValueError as exc:
                items.append(VlessBatchImportItem(index, "invalid", reason=str(exc)))
                failed += 1
                continue

            signatures.add(signature)
            current_count += 1
            items.append(VlessBatchImportItem(index, "imported", profile=saved))
            imported += 1

        return VlessBatchImportResult(
            limit=self.MAX_PROFILES,
            total=len(sources),
            imported=imported,
            failed=failed,
            duplicates=duplicates,
            limit_reached=limit_reached,
            items=items,
        )

    @staticmethod
    def _appliance_profile_source(row: dict[str, Any]) -> str:
        """Build a private VLESS URI from a row in the router-side profile store."""
        address = str(row.get("address") or "").strip()
        uuid = str(row.get("uuid") or "").strip()
        try:
            port = int(row.get("port"))
        except (TypeError, ValueError) as exc:
            raise ValueError("Профиль роутера содержит некорректный порт.") from exc
        if not address or not uuid or not 1 <= port <= 65535:
            raise ValueError(
                "Профиль роутера не содержит адрес, UUID или корректный порт."
            )
        host = (
            f"[{address}]"
            if ":" in address and not address.startswith("[")
            else address
        )
        reality = row.get("reality") if isinstance(row.get("reality"), dict) else None
        security = "reality" if reality else "none"
        params: dict[str, str] = {
            "encryption": "none",
            "type": str(row.get("network") or "tcp"),
            "security": security,
        }
        flow = row.get("flow")
        if flow:
            params["flow"] = str(flow)
        if reality:
            if reality.get("server_name"):
                params["sni"] = str(reality["server_name"])
            if reality.get("public_key"):
                params["pbk"] = str(reality["public_key"])
            params["sid"] = str(reality.get("short_id") or "")
            if reality.get("fingerprint"):
                params["fp"] = str(reality["fingerprint"])
        name = (
            str(row.get("name") or f"{address}:{port}").strip() or f"{address}:{port}"
        )
        return (
            f"vless://{quote(uuid, safe='')}@{host}:{port}?"
            f"{urlencode(params)}#{quote(name, safe='')}"
        )

    def _parse_appliance_store(
        self, store: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not isinstance(store, dict) or not isinstance(store.get("profiles"), list):
            raise ValueError("Формат профилей maxvpn.lan не распознан.")
        rows = store["profiles"]
        if len(rows) > self.MAX_PROFILES:
            raise ValueError("На роутере найдено больше 50 профилей.")
        parsed: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        seen_identities: set[tuple[Any, ...]] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(
                    "Хранилище maxvpn.lan содержит некорректную запись профиля."
                )
            raw_id = row.get("id")
            if isinstance(raw_id, bool):
                raise ValueError(
                    "Профиль maxvpn.lan содержит некорректный идентификатор."
                )
            try:
                profile_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Профиль maxvpn.lan содержит некорректный идентификатор."
                ) from exc
            if profile_id < 1 or profile_id in seen_ids:
                raise ValueError(
                    "Хранилище maxvpn.lan содержит повторяющиеся "
                    "идентификаторы профилей."
                )
            enabled = row.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError(
                    "Профиль maxvpn.lan содержит некорректное состояние enabled."
                )
            source = self._appliance_profile_source(row)
            server = self._importer.parse(source)
            name = self._validate_name(str(row.get("name") or server.name).strip())
            identity = self._server_identity(server)
            if identity in seen_identities:
                raise ValueError(
                    "Хранилище maxvpn.lan содержит дублирующиеся VLESS-профили."
                )
            seen_ids.add(profile_id)
            seen_identities.add(identity)
            parsed.append(
                {
                    "appliance_id": profile_id,
                    "name": name,
                    "enabled": enabled,
                    "server": server,
                }
            )

        settings = (
            store.get("settings") if isinstance(store.get("settings"), dict) else {}
        )
        interval = settings.get("urltest_interval", "3m")
        tolerance = settings.get("urltest_tolerance_ms", 50)
        if interval not in {"30s", "1m", "2m", "3m", "5m", "10m"}:
            raise ValueError(
                "Параметры URLTest на maxvpn.lan содержат недопустимый интервал."
            )
        if isinstance(tolerance, bool):
            raise ValueError(
                "Параметры URLTest на maxvpn.lan содержат некорректный допуск."
            )
        try:
            tolerance = int(tolerance)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Параметры URLTest на maxvpn.lan содержат некорректный допуск."
            ) from exc
        if not 0 <= tolerance <= 5000:
            raise ValueError(
                "Параметры URLTest на maxvpn.lan содержат недопустимый допуск."
            )
        return parsed, {"urltest_interval": interval, "urltest_tolerance_ms": tolerance}

    def appliance_sync_status(
        self, user_id: int, store: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare the local profile database with maxvpn.lan
        without exposing secrets."""
        remote, remote_settings = self._parse_appliance_store(store)
        local_records = self._records(user_id)
        local_by_identity: dict[tuple[Any, ...], tuple[Any, VlessServerConfig]] = {}
        for record in local_records:
            try:
                server = self._decrypt_server(record.encrypted_config)
            except ValueError as exc:
                raise ValueError(
                    "Локальный VLESS-профиль повреждён; синхронизация отменена."
                ) from exc
            identity = self._server_identity(server)
            local_by_identity.setdefault(identity, (record, server))

        remote_by_identity = {
            self._server_identity(item["server"]): item for item in remote
        }
        on_router_only = []
        local_only = []
        updated = []
        for identity, item in remote_by_identity.items():
            local = local_by_identity.get(identity)
            summary = {
                "name": item["name"],
                "address": item["server"].address,
                "port": item["server"].port,
                "enabled": item["enabled"],
            }
            if local is None:
                on_router_only.append({"appliance_id": item["appliance_id"], **summary})
                continue
            record, local_server = local
            if (
                str(record.name) != item["name"]
                or bool(record.enabled) != item["enabled"]
                or self._serialize_server(local_server)
                != self._serialize_server(item["server"])
            ):
                updated.append({"appliance_id": item["appliance_id"], **summary})

        for identity, (record, server) in local_by_identity.items():
            if identity not in remote_by_identity:
                local_only.append(
                    {
                        "id": int(record.id),
                        "name": str(record.name),
                        "address": server.address,
                        "port": server.port,
                        "enabled": bool(record.enabled),
                    }
                )

        local_settings = self.get_runtime_settings(user_id)
        settings_changed = local_settings != remote_settings
        required = bool(on_router_only or local_only or updated or settings_changed)
        return {
            "connected": True,
            "sync_required": required,
            "local_profile_count": len(local_records),
            "appliance_profile_count": len(remote),
            "on_router_only": on_router_only,
            "local_only": local_only,
            "updated": updated,
            "settings_changed": settings_changed,
            "local_settings": local_settings,
            "appliance_settings": remote_settings,
        }

    def synchronize_from_appliance(
        self, user_id: int, store: dict[str, Any]
    ) -> dict[str, Any]:
        """Reconcile local VLESS profiles/settings to the appliance's saved state.

        This updates only the localhost database. It never applies or restarts the
        router's sing-box configuration and refuses an empty router profile store
        to avoid accidental bulk deletion.
        """
        remote, remote_settings = self._parse_appliance_store(store)
        if not remote:
            raise ValueError(
                "На maxvpn.lan нет профилей; пустая синхронизация отменена, "
                "локальные данные сохранены."
            )
        if not any(item["enabled"] for item in remote):
            raise ValueError(
                "На maxvpn.lan нет включённых профилей; локальные данные сохранены."
            )

        local_records = self._records(user_id)
        local_by_identity: dict[tuple[Any, ...], Any] = {}
        for record in local_records:
            try:
                local_server = self._decrypt_server(record.encrypted_config)
            except ValueError as exc:
                raise ValueError(
                    "Локальный VLESS-профиль повреждён; "
                    "синхронизация отменена без изменений."
                ) from exc
            local_by_identity.setdefault(self._server_identity(local_server), record)

        remote_identities = {self._server_identity(item["server"]) for item in remote}
        imported = updated = deleted = unchanged = 0
        for item in remote:
            server = item["server"]
            identity = self._server_identity(server)
            record = local_by_identity.get(identity)
            if record is None:
                self._persist_server(user_id, server, item["name"], item["enabled"])
                imported += 1
                continue
            current_server = self._decrypt_server(record.encrypted_config)
            changed = (
                str(record.name) != item["name"]
                or bool(record.enabled) != item["enabled"]
                or self._serialize_server(current_server)
                != self._serialize_server(server)
            )
            if changed:
                record.name = item["name"]
                record.enabled = item["enabled"]
                record.encrypted_config = self._cipher.encrypt(
                    self._serialize_server(server)
                )
                self._repository.update(record)
                updated += 1
            else:
                unchanged += 1

        for record in local_records:
            try:
                identity = self._server_identity(
                    self._decrypt_server(record.encrypted_config)
                )
            except ValueError:
                # Validation above already rejected damaged records; keep this guard
                # to avoid deleting a profile if the data changed unexpectedly.
                continue
            if identity not in remote_identities:
                if self._repository.delete_for_user(user_id, int(record.id)):
                    deleted += 1

        local_settings = self.get_runtime_settings(user_id)
        if self._settings_repository is not None and local_settings != remote_settings:
            self.update_runtime_settings(
                user_id,
                remote_settings["urltest_interval"],
                remote_settings["urltest_tolerance_ms"],
            )
        settings_synchronized = self.get_runtime_settings(user_id) == remote_settings
        return {
            "imported": imported,
            "updated": updated,
            "deleted": deleted,
            "unchanged": unchanged,
            "profiles": len(remote),
            "settings_synchronized": settings_synchronized,
        }

    def appliance_profile_id_for_local_profile(
        self, user_id: int, profile_id: int, store: dict[str, Any]
    ) -> int | None:
        """Map a local database ID to the matching router-side outbound ID
        by identity."""
        record = self.get_profile(user_id, profile_id)
        if record is None:
            raise LookupError("vless_profile_not_found")
        local_server = self._decrypt_server(record.encrypted_config)
        identity = self._server_identity(local_server)
        remote, _ = self._parse_appliance_store(store)
        match = next(
            (
                item
                for item in remote
                if self._server_identity(item["server"]) == identity
            ),
            None,
        )
        return int(match["appliance_id"]) if match else None

    def local_profile_id_for_appliance_outbound(
        self, user_id: int, store: dict[str, Any], outbound: str | None
    ) -> int | None:
        """Map a router outbound tag to the local DB ID using full profile identity."""
        match = __import__("re").fullmatch(
            r"vless-profile-([1-9][0-9]*)", str(outbound or "")
        )
        if not match:
            return None
        target_id = int(match.group(1))
        remote, _ = self._parse_appliance_store(store)
        target = next(
            (item for item in remote if int(item["appliance_id"]) == target_id), None
        )
        if target is None:
            return None
        identity = self._server_identity(target["server"])
        for record in self._records(user_id):
            try:
                server = self._decrypt_server(record.encrypted_config)
            except ValueError:
                continue
            if self._server_identity(server) == identity:
                return int(record.id)
        return None

    def export_bundle(self, user_id: int) -> dict[str, Any]:
        """Export profile secrets explicitly for one-time migration to maxvpn.lan.

        The regular list/read APIs intentionally do not expose UUIDs or REALITY
        public keys. This separate authenticated export endpoint reconstructs
        importable VLESS links only when an administrator explicitly downloads
        the migration bundle.
        """
        records = self._records(user_id)
        profiles: list[dict[str, Any]] = []
        for record in records:
            server = self._decrypt_server(record.encrypted_config)
            host = server.address
            if ":" in host and not host.startswith("["):
                host = "[" + host + "]"
            params: dict[str, str] = {
                "encryption": "none",
                "type": server.network or "tcp",
                "security": "reality" if server.reality else "none",
            }
            if server.flow:
                params["flow"] = server.flow
            if server.reality:
                params["sni"] = server.reality.server_name
                if server.reality.fingerprint:
                    params["fp"] = server.reality.fingerprint
                params["pbk"] = server.reality.public_key
                params["sid"] = server.reality.short_id or ""
            source = (
                f"vless://{server.uuid}@{host}:{server.port}?"
                f"{urlencode(params)}#{quote(record.name, safe='')}"
            )
            profiles.append(
                {
                    "id": int(record.id),
                    "name": str(record.name),
                    "enabled": bool(record.enabled),
                    "source": source,
                }
            )
        return {
            "format": "maxvpn-vless-profiles",
            "version": 1,
            "profiles": profiles,
            "settings": self.get_runtime_settings(user_id),
            "warning": (
                "Contains VLESS UUIDs and REALITY connection parameters. "
                "Keep this file private."
            ),
        }

    def get(self, user_id: int) -> VlessProfileRead | None:
        records = self._records(user_id)
        if not records:
            return None
        profile = next((item for item in records if item.enabled), records[0])
        return self._to_read(profile, self._decrypt_server(profile.encrypted_config))

    def list(self, user_id: int) -> list[VlessProfileRead]:
        return [
            self._to_read(profile, self._decrypt_server(profile.encrypted_config))
            for profile in self._records(user_id)
        ]

    def get_profile(self, user_id: int, profile_id: int):
        return self._repository.get_by_id_for_user(user_id, profile_id)

    def get_server(self, user_id: int) -> VlessServerConfig | None:
        records = self._records(user_id)
        profile = next((item for item in records if item.enabled), None)
        if profile is None:
            return None
        return self._decrypt_server(profile.encrypted_config)

    def get_enabled_servers(self, user_id: int) -> list[tuple[int, VlessServerConfig]]:
        result: list[tuple[int, VlessServerConfig]] = []
        for profile in self._records(user_id):
            if profile.enabled:
                result.append(
                    (profile.id, self._decrypt_server(profile.encrypted_config))
                )
        return result

    def set_enabled(
        self, user_id: int, profile_id: int, enabled: bool
    ) -> VlessProfileRead:
        profile = self._repository.get_by_id_for_user(user_id, profile_id)
        if profile is None:
            raise LookupError("vless_profile_not_found")
        if profile.enabled and not enabled:
            enabled_records = [item for item in self._records(user_id) if item.enabled]
            if len(enabled_records) <= 1:
                raise ValueError("Нельзя отключить последний включённый VLESS-сервер")
        profile.enabled = enabled
        profile = self._repository.update(profile)
        return self._to_read(profile, self._decrypt_server(profile.encrypted_config))

    def delete(self, user_id: int, profile_id: int) -> None:
        profile = self._repository.get_by_id_for_user(user_id, profile_id)
        if profile is None:
            raise LookupError("vless_profile_not_found")
        if profile.enabled:
            enabled_records = [item for item in self._records(user_id) if item.enabled]
            if len(enabled_records) <= 1:
                raise ValueError("Нельзя удалить последний включённый VLESS-сервер")
        if not self._repository.delete_for_user(user_id, profile_id):
            raise LookupError("vless_profile_not_found")

    @staticmethod
    def _utc_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _iso_timestamp(cls, value: datetime | None) -> str | None:
        normalized = cls._utc_datetime(value)
        return normalized.isoformat().replace("+00:00", "Z") if normalized else None

    @classmethod
    def _delay_history_item(cls, profile: Any, now: datetime) -> dict[str, Any]:
        first_failed_at = cls._utc_datetime(profile.first_failed_at)
        unavailable_seconds = (
            max(0, int((now - first_failed_at).total_seconds()))
            if first_failed_at is not None
            else None
        )
        last_checked_at = cls._utc_datetime(profile.last_checked_at)
        return {
            "profile_id": int(profile.id),
            "delay_ms": profile.last_delay_ms,
            "reachable": bool(
                last_checked_at
                and profile.last_delay_ms is not None
                and first_failed_at is None
            ),
            "first_failed_at": cls._iso_timestamp(profile.first_failed_at),
            "last_checked_at": cls._iso_timestamp(profile.last_checked_at),
            "last_success_at": cls._iso_timestamp(profile.last_success_at),
            "last_outage_started_at": cls._iso_timestamp(
                profile.last_outage_started_at
            ),
            "last_recovered_at": cls._iso_timestamp(profile.last_recovered_at),
            "last_outage_duration_seconds": profile.last_outage_duration_seconds,
            "consecutive_failures": int(profile.consecutive_failures or 0),
            "unavailable_seconds": unavailable_seconds,
        }

    def record_delay_results(
        self,
        user_id: int,
        measurements: dict[int, int | None],
        checked_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Persist the latest probe results and maintain consecutive outage windows."""
        now = self._utc_datetime(checked_at or datetime.now(timezone.utc))
        assert now is not None
        records = self._repository.list_by_user(user_id)
        by_id = {int(record.id): record for record in records}
        changed = []

        for profile_id, delay in measurements.items():
            record = by_id.get(int(profile_id))
            if record is None:
                continue
            if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
                delay = None

            if delay is None:
                if record.first_failed_at is None:
                    record.first_failed_at = now
                    record.last_outage_started_at = now
                record.consecutive_failures = int(record.consecutive_failures or 0) + 1
                record.last_delay_ms = None
            else:
                if record.first_failed_at is not None:
                    started = self._utc_datetime(record.first_failed_at)
                    if started is not None:
                        record.last_outage_duration_seconds = max(
                            0, int((now - started).total_seconds())
                        )
                    record.last_outage_started_at = started or record.first_failed_at
                    record.last_recovered_at = now
                record.first_failed_at = None
                record.consecutive_failures = 0
                record.last_delay_ms = delay
                record.last_success_at = now

            record.last_checked_at = now
            changed.append(record)

        self._repository.update_many(changed)
        return [self._delay_history_item(record, now) for record in changed]

    def get_delay_history(self, user_id: int) -> list[dict[str, Any]]:
        """Return persisted monitoring state without triggering new probes."""
        now = datetime.now(timezone.utc)
        records = self._repository.list_by_user(user_id)
        return [
            self._delay_history_item(record, now)
            for record in records
            if record.last_checked_at is not None
        ]

    @staticmethod
    def _settings_payload(settings: Any) -> dict[str, Any]:
        return {
            "urltest_interval": settings.urltest_interval,
            "urltest_tolerance_ms": settings.urltest_tolerance_ms,
        }

    def get_runtime_settings(self, user_id: int) -> dict[str, Any]:
        if self._settings_repository is None:
            return {"urltest_interval": "3m", "urltest_tolerance_ms": 50}
        settings = self._settings_repository.get_or_create_for_user(user_id)
        return self._settings_payload(settings)

    def update_runtime_settings(
        self,
        user_id: int,
        urltest_interval: str,
        urltest_tolerance_ms: int,
    ) -> dict[str, Any]:
        if self._settings_repository is None:
            raise RuntimeError("VLESS runtime settings repository is not configured")
        if urltest_interval not in {"30s", "1m", "2m", "3m", "5m", "10m"}:
            raise ValueError("Unsupported URLTest interval")
        if not 0 <= urltest_tolerance_ms <= 5000:
            raise ValueError("URLTest tolerance must be between 0 and 5000 ms")
        settings = self._settings_repository.get_or_create_for_user(user_id)
        settings.urltest_interval = urltest_interval
        settings.urltest_tolerance_ms = urltest_tolerance_ms
        updated = self._settings_repository.update(settings)
        return self._settings_payload(updated)

    def validate(self, source: str) -> VlessProfileValidation:
        try:
            server = self._importer.parse(source)
        except ValueError as exc:
            return VlessProfileValidation(valid=False, reason=str(exc))

        reality = server.reality
        return VlessProfileValidation(
            valid=True,
            name=server.name,
            address=server.address,
            port=server.port,
            flow=server.flow,
            security="reality" if reality else "none",
            server_name=reality.server_name if reality else None,
            fingerprint=reality.fingerprint if reality else None,
        )

    def _persist_server(
        self,
        user_id: int,
        server: VlessServerConfig,
        name: str,
        enabled: bool,
    ) -> VlessProfileRead:
        encrypted = self._cipher.encrypt(self._serialize_server(server))
        profile = self._repository.create_for_user(
            user_id=user_id,
            name=name,
            encrypted_config=encrypted,
            enabled=enabled,
        )
        return self._to_read(profile, server)

    def _records(self, user_id: int) -> list[Any]:
        list_method = getattr(self._repository, "list_by_user", None)
        if callable(list_method):
            return list(list_method(user_id))
        # Compatibility for light-weight repository doubles in older tests.
        profile = self._repository.get_by_user(user_id)
        return [profile] if profile is not None else []

    @staticmethod
    def _validate_name(name: str) -> str:
        profile_name = name.strip()
        if not profile_name:
            raise ValueError("VLESS profile name must not be empty")
        if len(profile_name) > 100:
            raise ValueError("VLESS profile name must not exceed 100 characters")
        return profile_name

    @staticmethod
    def _server_identity(server: VlessServerConfig) -> tuple[Any, ...]:
        reality = server.reality
        return (
            server.address.lower(),
            server.port,
            server.uuid,
            server.flow,
            server.network,
            reality.server_name.lower() if reality else None,
            reality.public_key if reality else None,
            reality.short_id if reality else None,
        )

    @staticmethod
    def _serialize_server(server: VlessServerConfig) -> str:
        payload = {
            "name": server.name,
            "address": server.address,
            "port": server.port,
            "uuid": server.uuid,
            "flow": server.flow,
            "network": server.network,
            "reality": asdict(server.reality) if server.reality else None,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _deserialize_server(plaintext: str) -> VlessServerConfig:
        try:
            payload = json.loads(plaintext)
            if not isinstance(payload, dict):
                raise ValueError("stored configuration must be an object")
            reality_payload = payload.get("reality")
            reality = None
            if reality_payload is not None:
                if not isinstance(reality_payload, dict):
                    raise ValueError("stored REALITY configuration is invalid")
                reality = VlessRealityConfig(
                    public_key=reality_payload["public_key"],
                    server_name=reality_payload["server_name"],
                    short_id=reality_payload["short_id"],
                    fingerprint=reality_payload.get("fingerprint"),
                )
            return VlessServerConfig(
                name=payload["name"],
                address=payload["address"],
                port=payload["port"],
                uuid=payload["uuid"],
                flow=payload.get("flow"),
                network=payload.get("network", "tcp"),
                reality=reality,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Stored VLESS profile is invalid") from exc

    def _decrypt_server(self, encrypted_config: str) -> VlessServerConfig:
        return self._deserialize_server(self._cipher.decrypt(encrypted_config))

    @staticmethod
    def _to_read(profile, server: VlessServerConfig) -> VlessProfileRead:
        reality = server.reality
        return VlessProfileRead(
            id=profile.id,
            name=profile.name,
            enabled=profile.enabled,
            address=server.address,
            port=server.port,
            flow=server.flow,
            security="reality" if reality else "none",
            server_name=reality.server_name if reality else None,
            fingerprint=reality.fingerprint if reality else None,
            has_uuid=bool(server.uuid),
        )
