from __future__ import annotations

from ..base import Policy
from ..context import PolicyContext
from ..result import PolicyResult


class LoadPolicy(Policy):
    """Checks server load."""

    def check(self, context: PolicyContext) -> PolicyResult:
        return PolicyResult.allow()
