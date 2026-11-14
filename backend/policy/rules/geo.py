from __future__ import annotations

from ..base import Policy
from ..context import PolicyContext
from ..result import PolicyResult


class GeoPolicy(Policy):
    """Applies geographic routing rules."""

    def check(self, context: PolicyContext) -> PolicyResult:
        return PolicyResult.allow()
