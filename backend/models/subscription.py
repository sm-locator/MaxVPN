from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(slots=True)
class Subscription:
    """
    Represents a user's VPN subscription.
    """

    id: int

    plan: str

    active: bool

    expires_at: datetime

    device_limit: int

    def is_expired(self) -> bool:
        """
        Returns True if the subscription has expired.
        """

        return datetime.now(UTC) >= self.expires_at

    @property
    def valid(self) -> bool:
        """
        Returns True when the subscription is active
        and has not expired.
        """

        return self.active and not self.is_expired()
