from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SmartRoutingRuleData:
    target_type: str
    target: str
    action: str
    priority: int
    address_family: str
    enabled: bool
