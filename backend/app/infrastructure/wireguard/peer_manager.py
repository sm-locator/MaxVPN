from ipaddress import IPv4Address

from app.infrastructure.executor import CommandExecutor
from app.vpn.repositories import WireGuardPeerManager


class SystemWireGuardPeerManager(WireGuardPeerManager):
    def __init__(
        self,
        executor: CommandExecutor,
        interface_name: str,
    ) -> None:
        self._executor = executor
        self._interface_name = interface_name

    def add_peer(
        self,
        public_key: str,
        address: IPv4Address,
    ) -> None:
        self._executor.run(
            [
                "wg",
                "set",
                self._interface_name,
                "peer",
                public_key,
                "allowed-ips",
                f"{address}/32",
            ]
        )

    def remove_peer(
        self,
        public_key: str,
    ) -> None:
        self._executor.run(
            [
                "wg",
                "set",
                self._interface_name,
                "peer",
                public_key,
                "remove",
            ]
        )
