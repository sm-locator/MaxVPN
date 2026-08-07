from __future__ import annotations

from ..base import Policy
from ..context import PolicyContext
from ..result import PolicyResult


class ServerPolicy(Policy):
    """Selects an appropriate VPN server."""

    def check(self, context: PolicyContext) -> PolicyResult:
        return PolicyResult.allow()
