from __future__ import annotations

from ..base import Policy
from ..codes import PolicyCode
from ..context import PolicyContext
from ..result import PolicyResult


class SubscriptionPolicy(Policy):
    """Checks whether the user has a valid subscription."""

    def check(self, context: PolicyContext) -> PolicyResult:

        if not context.user.active:
            return PolicyResult.deny(
                code=PolicyCode.USER_DISABLED,
                message="User account is disabled",
            )

        if context.user.subscription is None:
            return PolicyResult.deny(
                code=PolicyCode.SUBSCRIPTION_NOT_FOUND,
                message="Subscription not found",
            )

        if not context.user.subscription.active:
            return PolicyResult.deny(
                code=PolicyCode.SUBSCRIPTION_DISABLED,
                message="Subscription is disabled",
            )

        if context.user.subscription.is_expired():
            return PolicyResult.deny(
                code=PolicyCode.SUBSCRIPTION_EXPIRED,
                message="Subscription has expired",
            )

        return PolicyResult.allow()
