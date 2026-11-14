from __future__ import annotations

from typing import Protocol


class VpnRuntimeTrafficController(Protocol):
    def enable_vpn_mode(self) -> None: ...

    def enable_wan_mode(self) -> None: ...
