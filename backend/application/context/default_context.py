from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.models.device import Device
from backend.models.server import Server
from backend.models.subscription import Subscription
from backend.models.user import User
from backend.policy.context import PolicyContext


def create_default_context() -> PolicyContext:
    """
    Default context used by CLI and API.

    Tests may build custom contexts using their own factories.
    """

    subscription = Subscription(
        id=1,
        plan="premium",
        active=True,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        device_limit=5,
    )

    user = User(
        id=1,
        username="maks",
        active=True,
        subscription=subscription,
    )

    device = Device(
        id=1,
        name="Windows PC",
        fingerprint="device-001",
        active=True,
        trusted=True,
    )

    server = Server(
        id=1,
        name="Warsaw-01",
        country="PL",
        city="Warsaw",
        endpoint="1.2.3.4:51820",
        public_key="server-public-key",
        online=True,
    )

    return PolicyContext(
        user=user,
        device=device,
        server=server,
    )
