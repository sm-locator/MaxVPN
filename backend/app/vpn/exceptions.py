class NoAvailableIPAddressError(Exception):
    """Raised when there are no free IP addresses in the network."""


class ClientNotFoundError(Exception):
    """Raised when a WireGuard client does not exist."""
