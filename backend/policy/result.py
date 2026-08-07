from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PolicyResult:
    """
    Result of a policy evaluation.

    Attributes:
        allowed: Whether the request is allowed.
        code: Machine-readable result code.
        message: Human-readable description.
        data: Optional payload for downstream processing.
    """

    allowed: bool
    code: str = "OK"
    message: str = ""
    data: dict[str, Any] | None = None

    @classmethod
    def allow(
        cls,
        *,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> "PolicyResult":
        return cls(
            allowed=True,
            code="OK",
            message=message,
            data=data,
        )

    @classmethod
    def deny(
        cls,
        code: str,
        message: str,
        *,
        data: dict[str, Any] | None = None,
    ) -> "PolicyResult":
        return cls(
            allowed=False,
            code=code,
            message=message,
            data=data,
        )
