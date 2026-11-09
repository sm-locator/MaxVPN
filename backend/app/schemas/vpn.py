from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VpnProfileUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    provider_config: str = Field(min_length=1)


class VpnProfileValidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_config: str = Field(min_length=1)


class VpnProfileReadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    enabled: bool
    has_private_key: bool
    has_preshared_key: bool


class VpnProfileValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    interface_address: str | None
    endpoint: str | None
    allowed_ips: list[str]
    has_private_key: bool
    has_preshared_key: bool
    reason: str | None


class VpnProfileApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied: bool
    verified: bool
    no_change: bool = False
    rolled_back: bool
    rollback_verified: bool
    health_failed: bool
    reason: str | None


class VpnProfileConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool

    address: str
    dns: str | None
    mtu: int | None

    jc: int | None
    jmin: int | None
    jmax: int | None

    s1: int | None
    s2: int | None
    s3: int | None
    s4: int | None

    h1: str | None
    h2: str | None
    h3: str | None
    h4: str | None

    i1: str | None
    i2: str | None
    i3: str | None
    i4: str | None
    i5: str | None

    public_key: str
    allowed_ips: list[str]
    persistent_keepalive: int | None
    endpoint: str


class VpnProfileConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True

    address: str = Field(min_length=1)
    dns: str | None = None
    mtu: int | None = None

    jc: int | None = None
    jmin: int | None = None
    jmax: int | None = None

    s1: int | None = None
    s2: int | None = None
    s3: int | None = None
    s4: int | None = None

    h1: str | None = None
    h2: str | None = None
    h3: str | None = None
    h4: str | None = None

    i1: str | None = None
    i2: str | None = None
    i3: str | None = None
    i4: str | None = None
    i5: str | None = None

    public_key: str = Field(min_length=1)
    allowed_ips: list[str] = Field(min_length=1)
    persistent_keepalive: int | None = None
    endpoint: str = Field(min_length=1)


class VpnRuntimeModeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["vpn", "wan", "vless"]


class VpnRuntimeModeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["vpn", "wan", "vless"]
    message: str


class VpnRuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interface: str
    healthy: bool
    interface_exists: bool
    interface_up: bool
    traffic_mode: Literal["vpn", "wan", "vless"]
    expected_peer_found: bool
    expected_endpoint: bool
    endpoint_route_ok: bool

    listen_port: int | None
    latest_handshake: datetime | None
    handshake_age_seconds: int | None
    rx_bytes: int
    tx_bytes: int

    reason: str | None
    checked_at: datetime
    in_sync: bool
