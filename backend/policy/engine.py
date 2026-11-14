from __future__ import annotations

from collections.abc import Iterable

from .base import Policy
from .context import PolicyContext
from .result import PolicyResult


class PolicyEngine:
    """
    Executes policies in order.

    Stops immediately on the first denied policy
    (fail-fast strategy).
    """

    def __init__(self, policies: Iterable[Policy] | None = None) -> None:
        self._policies: list[Policy] = list(policies or [])

    def register(self, policy: Policy) -> None:
        """
        Register a policy at the end of the pipeline.
        """
        self._policies.append(policy)

    def execute(self, context: PolicyContext) -> PolicyResult:
        """
        Execute all registered policies.

        Returns the first denied PolicyResult or
        PolicyResult.allow() if every policy passes.
        """

        for policy in self._policies:
            result = policy.check(context)

            if not result.allowed:
                return result

        return PolicyResult.allow()

    def clear(self) -> None:
        """
        Remove all registered policies.
        """
        self._policies.clear()

    @property
    def policies(self) -> tuple[Policy, ...]:
        """
        Read-only view of registered policies.
        """
        return tuple(self._policies)
