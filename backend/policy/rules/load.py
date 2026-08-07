from __future__ import annotations

from ..base import Policy
from ..codes import PolicyCode
from ..context import PolicyContext
from ..result import PolicyResult


class LoadPolicy(Policy):
    """
    Checks whether the server load is acceptable.
    """

    def check(self, context: PolicyContext) -> PolicyResult:
        server = context.server

        # ServerPolicy already checks that a server exists.
        if server is None:
            return PolicyResult.allow()

        if server.load >= server.max_load:
            return PolicyResult.deny(
                PolicyCode.SERVER_OVERLOADED,
                "Server is overloaded.",
            )

        return PolicyResult.allow()
