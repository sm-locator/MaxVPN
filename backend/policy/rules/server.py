from __future__ import annotations

from ..base import Policy
from ..codes import PolicyCode
from ..context import PolicyContext
from ..result import PolicyResult


class ServerPolicy(Policy):
    """Checks server availability."""

    def check(self, context: PolicyContext) -> PolicyResult:
        server = context.server

        if server is None:
            return PolicyResult.deny(
                PolicyCode.SERVER_UNAVAILABLE,
                "Server not found.",
            )

        if not server.online:
            return PolicyResult.deny(
                PolicyCode.SERVER_OFFLINE,
                "Server is offline.",
            )

        if server.maintenance:
            return PolicyResult.deny(
                PolicyCode.SERVER_MAINTENANCE,
                "Server is under maintenance.",
            )

        return PolicyResult.allow()
