from __future__ import annotations

from dataclasses import dataclass

from backend.models.device import Device
from backend.models.server import Server
from backend.models.user import User


@dataclass(slots=True)
class PolicyContext:
    """
    Shared context passed through all policies.
    """

    user: User | None = None
    device: Device | None = None
    server: Server | None = None
