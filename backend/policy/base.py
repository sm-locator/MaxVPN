from __future__ import annotations

from abc import ABC, abstractmethod

from .context import PolicyContext
from .result import PolicyResult


class Policy(ABC):
    """
    Base class for all policies.

    Every policy receives a PolicyContext and returns
    a PolicyResult.
    """

    @abstractmethod
    def check(self, context: PolicyContext) -> PolicyResult:
        """
        Evaluate the policy.

        Args:
            context: Shared policy context.

        Returns:
            PolicyResult
        """
        raise NotImplementedError
