from datetime import UTC, datetime, timedelta

from backend.models.subscription import Subscription


def test_subscription_is_valid():
    subscription = Subscription(
        id=1,
        plan="premium",
        active=True,
        expires_at=datetime.now(UTC) + timedelta(days=30),
        device_limit=5,
    )

    assert subscription.valid is True


def test_subscription_is_expired():
    subscription = Subscription(
        id=1,
        plan="premium",
        active=True,
        expires_at=datetime.now(UTC) - timedelta(days=1),
        device_limit=5,
    )

    assert subscription.valid is False
