from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class VlessProfileImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=200_000)
    name: str | None = Field(default=None, max_length=100)
    enabled: bool = True


class VlessProfileValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(min_length=1, max_length=200_000)


class VlessProfileBatchImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(min_length=1, max_length=50)


class VlessProfileEnabledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class VlessProfileSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # null means automatic selection via the sing-box URLTest group.
    profile_id: int | None = None


class VlessApplianceSyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_delete_local_only: bool = False


class VlessApplianceKillSwitchUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class VlessProfileReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
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


class VlessProfileValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valid: bool
    name: str | None = None
    address: str | None = None
    port: int | None = None
    flow: str | None = None
    security: str | None = None
    server_name: str | None = None
    fingerprint: str | None = None
    reason: str | None = None


class VlessProfileBatchImportItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int
    status: Literal["imported", "invalid", "duplicate", "limit_reached"]
    profile: VlessProfileReadResponse | None = None
    reason: str | None = None


class VlessProfileBatchImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limit: int
    total: int
    imported: int
    failed: int
    duplicates: int
    limit_reached: int
    items: list[VlessProfileBatchImportItemResponse]


class VlessProfileDelayItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_id: int
    delay_ms: int | None
    reachable: bool
    first_failed_at: str | None = None
    last_checked_at: str | None = None
    last_success_at: str | None = None
    last_outage_started_at: str | None = None
    last_recovered_at: str | None = None
    last_outage_duration_seconds: int | None = None
    consecutive_failures: int = 0
    unavailable_seconds: int | None = None


class VlessProfileDelayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[VlessProfileDelayItemResponse]


class VlessRuntimeSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urltest_interval: Literal["30s", "1m", "2m", "3m", "5m", "10m"] = "3m"
    urltest_tolerance_ms: int = Field(default=50, ge=0, le=5000)


class VlessRuntimeSettingsReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urltest_interval: Literal["30s", "1m", "2m", "3m", "5m", "10m"]
    urltest_tolerance_ms: int = Field(ge=0, le=5000)


class VlessRuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installed: bool
    running: bool
    interface: str
    lan_routing_enabled: bool
    message: str
    action: str | None = None
    prepared: bool | None = None
    selected_outbound: str | None = None
    selected_profile_id: int | None = None
    active_outbound: str | None = None
    active_server_name: str | None = None
    active_server_address: str | None = None
    active_server_port: int | None = None
    selection_mode: Literal["auto", "manual", "legacy", "unknown"] | None = None
    runtime_config_mode: (
        Literal["multi_profile", "single_profile", "unknown"] | None
    ) = None


class VlessSelectionHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monitor: dict[str, Any]
    current: dict[str, Any] | None
    events: list[dict[str, Any]]
    # Keys are appliance outbound tags; values are localhost DB profile IDs.
    profile_id_map: dict[str, int] = Field(default_factory=dict)
    # Per-profile URLTest availability state supplied by the Brume appliance.
    # Keep the nested payload flexible across appliance versions.
    profile_availability: dict[str, Any] = Field(default_factory=dict)
