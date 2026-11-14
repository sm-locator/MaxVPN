from backend.services.static_address_allocator import (
    StaticAddressAllocator,
)


def test_allocator_returns_address():
    allocator = StaticAddressAllocator()

    assert allocator.allocate() == "10.100.0.2/32"
