from unittest.mock import Mock

import pytest

from backend.services.database_address_allocator import (
    DatabaseAddressAllocator,
)


def test_allocator_returns_first_available_address():
    repository = Mock()
    repository.get_used_addresses.return_value = set()

    allocator = DatabaseAddressAllocator(repository)

    assert allocator.allocate() == "10.100.0.2/32"


def test_allocator_skips_used_addresses():
    repository = Mock()
    repository.get_used_addresses.return_value = {
        "10.100.0.2/32",
        "10.100.0.3/32",
    }

    allocator = DatabaseAddressAllocator(repository)

    assert allocator.allocate() == "10.100.0.4/32"


def test_allocator_fills_gap():
    repository = Mock()
    repository.get_used_addresses.return_value = {
        "10.100.0.2/32",
        "10.100.0.4/32",
    }

    allocator = DatabaseAddressAllocator(repository)

    assert allocator.allocate() == "10.100.0.3/32"


def test_allocator_raises_when_pool_is_exhausted():
    repository = Mock()
    repository.get_used_addresses.return_value = {
        "10.100.0.2/32",
        "10.100.0.3/32",
        "10.100.0.4/32",
    }

    allocator = DatabaseAddressAllocator(
        repository,
        network="10.100.0.0/30",
        first_host=2,
    )

    with pytest.raises(RuntimeError, match="No free client addresses"):
        allocator.allocate()
