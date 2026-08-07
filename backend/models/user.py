from __future__ import annotations

from dataclasses import dataclass

from .subscription import Subscription


@dataclass(slots=True)
class User:
    """
    Represents a VPN user.
    """

    id: int

    username: str

    active: bool

    subscription: Subscription | None = None
