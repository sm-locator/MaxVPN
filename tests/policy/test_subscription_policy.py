from datetime import UTC, datetime, timedelta

from backend.models.user import User
from backend.policy.codes import PolicyCode
from backend.policy.context import PolicyContext
from backend.policy.rules.subscription import SubscriptionPolicy

from tests.factories import (
    make_subscription,
    make_user,
)


def test_subscription_policy_allows_valid_user():
    policy = SubscriptionPolicy()

    context = PolicyContext(user=make_user())

    result = policy.check(context)

    assert result.allowed is True
    assert result.code == PolicyCode.OK


def test_subscription_policy_denies_disabled_user():
    policy = SubscriptionPolicy()

    context = PolicyContext(user=make_user(active=False))

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.USER_DISABLED


def test_subscription_policy_denies_missing_subscription():
    policy = SubscriptionPolicy()

    user = User(
        id=1,
        username="maks",
        active=True,
        subscription=None,
    )

    result = policy.check(PolicyContext(user=user))

    assert result.allowed is False
    assert result.code == PolicyCode.SUBSCRIPTION_NOT_FOUND


def test_subscription_policy_denies_disabled_subscription():
    policy = SubscriptionPolicy()

    subscription = make_subscription(active=False)

    result = policy.check(PolicyContext(user=make_user(subscription=subscription)))

    assert result.allowed is False
    assert result.code == PolicyCode.SUBSCRIPTION_DISABLED


def test_subscription_policy_denies_expired_subscription():
    policy = SubscriptionPolicy()

    subscription = make_subscription(expires_at=datetime.now(UTC) - timedelta(days=1))

    result = policy.check(PolicyContext(user=make_user(subscription=subscription)))

    assert result.allowed is False
    assert result.code == PolicyCode.SUBSCRIPTION_EXPIRED
