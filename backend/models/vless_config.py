from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VlessRealityConfig:
    public_key: str
    server_name: str
    short_id: str
    fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class VlessServerConfig:
    name: str
    address: str
    port: int
    uuid: str
    flow: str | None = None
    network: str = "tcp"
    reality: VlessRealityConfig | None = None
