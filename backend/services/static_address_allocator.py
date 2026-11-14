from __future__ import annotations

from backend.ports.address_allocator import AddressAllocator


class StaticAddressAllocator(AddressAllocator):
    """
    Returns a fixed address for tests.
    """

    def allocate(self) -> str:
        return "10.100.0.2/32"
