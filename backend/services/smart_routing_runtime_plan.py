from __future__ import annotations

from dataclasses import dataclass

from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.services.smart_routing_runtime_diff import (
    SmartRoutingRuntimeDiff,
    SmartRoutingRuntimeDiffService,
)
from backend.services.smart_routing_runtime_preview import (
    SmartRoutingRuntimePreview,
    SmartRoutingRuntimePreviewService,
)
from backend.services.smart_routing_runtime_state import (
    SmartRoutingRuntimeState,
    SmartRoutingRuntimeStateCollector,
)


@dataclass(frozen=True, slots=True)
class SmartRoutingRuntimePlan:
    current: SmartRoutingRuntimeState
    desired: SmartRoutingRuntimePreview
    diff: SmartRoutingRuntimeDiff

    @property
    def has_changes(self) -> bool:
        return self.diff.has_changes

    def render(self) -> str:
        action = (
            "REPLACE MAXVPN_DIRECT_STATIC"
            if self.diff.ipv4_replace_required
            else "NO CHANGE"
        )

        lines: list[str] = [
            "SMART ROUTING RUNTIME DIFF",
            "",
            "IPv4",
            f"  current addresses: {len(self.diff.current_ipv4_addresses)}",
            f"  desired networks:   {len(self.diff.desired_ipv4_networks)}",
            f"  covered addresses:  {len(self.diff.covered_ipv4_addresses)}",
            f"  stale addresses:    {len(self.diff.stale_ipv4_addresses)}",
            f"  action:             {action}",
            "",
        ]

        if self.diff.desired_ipv4_networks:
            lines.append("  desired networks:")
            lines.extend(
                f"    {network}" for network in self.diff.desired_ipv4_networks
            )
            lines.append("")

        if self.diff.stale_ipv4_addresses:
            lines.append("  stale current addresses:")
            lines.extend(
                f"    - {address}" for address in self.diff.stale_ipv4_addresses
            )
            lines.append("")

        lines.extend(
            [
                "DOMAINS",
                f"  added:     {len(self.diff.added_domains)}",
                f"  removed:   {len(self.diff.removed_domains)}",
                f"  unchanged: {len(self.diff.unchanged_domains)}",
                "",
            ]
        )

        if self.diff.added_domains:
            lines.append("  + added:")
            lines.extend(f"    + {domain}" for domain in self.diff.added_domains)
            lines.append("")

        if self.diff.removed_domains:
            lines.append("  - removed:")
            lines.extend(f"    - {domain}" for domain in self.diff.removed_domains)
            lines.append("")

        if self.diff.unchanged_domains:
            lines.append("  = unchanged:")
            lines.extend(f"    = {domain}" for domain in self.diff.unchanged_domains)
            lines.append("")

        lines.append(
            f"RESULT: {'CHANGES REQUIRED' if self.has_changes else 'NO CHANGES'}"
        )

        return "\n".join(lines)


class SmartRoutingRuntimePlanService:
    """
    Builds a read-only runtime plan.

    This service only reads the current runtime state and calculates the
    desired state. It never applies commands to OpenWrt.
    """

    def __init__(
        self,
        state_collector: SmartRoutingRuntimeStateCollector,
        preview_service: SmartRoutingRuntimePreviewService | None = None,
        diff_service: SmartRoutingRuntimeDiffService | None = None,
    ) -> None:
        self._state_collector = state_collector
        self._preview_service = preview_service or SmartRoutingRuntimePreviewService()
        self._diff_service = diff_service or SmartRoutingRuntimeDiffService()

    def build(self, policy: TrafficRoutingPolicy) -> SmartRoutingRuntimePlan:
        current = self._state_collector.collect()
        desired = self._preview_service.build(policy)
        diff = self._diff_service.build(current, desired)

        return SmartRoutingRuntimePlan(
            current=current,
            desired=desired,
            diff=diff,
        )
