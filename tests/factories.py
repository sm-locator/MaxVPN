from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.models.subscription import Subscription
from backend.models.user import User
from backend.models.device import Device
from backend.models.server import Server
from backend.policy.context import PolicyContext
from backend.models.server_metrics import ServerMetrics

_DEFAULT = object()


def make_subscription(
    *,
    id: int = 1,
    plan: str = "premium",
    active: bool = True,
    expires_at: datetime | None = None,
    device_limit: int = 5,
) -> Subscription:
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(days=30)

    return Subscription(
        id=id,
        plan=plan,
        active=active,
        expires_at=expires_at,
        device_limit=device_limit,
    )


def make_user(
    *,
    id: int = 1,
    username: str = "maks",
    active: bool = True,
    subscription: Subscription | None | object = _DEFAULT,
) -> User:

    if subscription is _DEFAULT:
        subscription = make_subscription()

    return User(
        id=id,
        username=username,
        active=active,
        subscription=subscription,
    )


def make_device(
    *,
    id: int = 1,
    name: str = "Windows PC",
    fingerprint: str = "device-001",
    active: bool = True,
    trusted: bool = True,
) -> Device:
    return Device(
        id=id,
        name=name,
        fingerprint=fingerprint,
        active=active,
        trusted=trusted,
    )


def make_server(
    *,
    id: int = 1,
    name: str = "Warsaw-01",
    country: str = "PL",
    city: str = "Warsaw",
    online: bool = True,
    load: int = 0,
    latency: int = 0,
    max_load: int = 80,
    max_devices: int = 1000,
    maintenance: bool = False,
    metrics: ServerMetrics | None = None,
) -> Server:
    return Server(
        id=id,
        name=name,
        country=country,
        city=city,
        online=online,
        load=load,
        latency=latency,
        max_load=max_load,
        max_devices=max_devices,
        maintenance=maintenance,
        metrics=metrics,
    )


def make_context(
    *,
    user=_DEFAULT,
    device=_DEFAULT,
    server=_DEFAULT,
) -> PolicyContext:

    if user is _DEFAULT:
        user = make_user()

    if device is _DEFAULT:
        device = make_device(
            trusted=True,
        )

    if server is _DEFAULT:
        server = make_server()

    return PolicyContext(
        user=user,
        device=device,
        server=server,
    )
