from __future__ import annotations

from ..base import Policy
from ..codes import PolicyCode
from ..context import PolicyContext
from ..result import PolicyResult


class DevicePolicy(Policy):
    """Checks device restrictions."""

    def check(self, context: PolicyContext) -> PolicyResult:
        if context.device is None:
            return PolicyResult.deny(
                code=PolicyCode.DEVICE_NOT_FOUND,
                message="Device not found.",
            )

        if not context.device.active:
            return PolicyResult.deny(
                code=PolicyCode.DEVICE_DISABLED,
                message="Device is disabled.",
            )

        if not context.device.trusted:
            return PolicyResult.deny(
                code=PolicyCode.DEVICE_UNTRUSTED,
                message="Device is not trusted.",
            )

        return PolicyResult.allow()
