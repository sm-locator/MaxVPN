from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AmneziaWGInterface:
    private_key: str
    address: str
    mtu: int | None = None
    dns: str | None = None

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


@dataclass(frozen=True, slots=True)
class AmneziaWGPeer:
    public_key: str
    allowed_ips: tuple[str, ...]
    endpoint: str
    persistent_keepalive: int | None = None
    preshared_key: str | None = None


@dataclass(frozen=True, slots=True)
class AmneziaWGConfig:
    interface: AmneziaWGInterface
    peer: AmneziaWGPeer
