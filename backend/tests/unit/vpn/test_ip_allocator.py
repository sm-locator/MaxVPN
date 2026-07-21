from ipaddress import IPv4Address, IPv4Network

import pytest

from app.vpn.exceptions import NoAvailableIPAddressError
from app.vpn.ip_allocator import IPAllocator


def test_allocate_skips_used_addresses() -> None:
    allocator = IPAllocator()

    network = IPv4Network("10.8.0.0/29")

    used = {
        IPv4Address("10.8.0.1"),
        IPv4Address("10.8.0.2"),
    }

    result = allocator.allocate(
        network=network,
        used_addresses=used,
    )

    assert result == IPv4Address("10.8.0.3")


def test_allocate_first_host() -> None:
    allocator = IPAllocator()

    network = IPv4Network("10.8.0.0/29")

    result = allocator.allocate(
        network=network,
        used_addresses=set(),
    )

    assert result == IPv4Address("10.8.0.1")


def test_allocate_last_host() -> None:
    allocator = IPAllocator()

    network = IPv4Network("10.8.0.0/29")

    used = {
        IPv4Address("10.8.0.1"),
        IPv4Address("10.8.0.2"),
        IPv4Address("10.8.0.3"),
        IPv4Address("10.8.0.4"),
        IPv4Address("10.8.0.5"),
    }

    result = allocator.allocate(
        network=network,
        used_addresses=used,
    )

    assert result == IPv4Address("10.8.0.6")


def test_allocate_when_network_is_full() -> None:
    allocator = IPAllocator()

    network = IPv4Network("10.8.0.0/30")

    used = {
        IPv4Address("10.8.0.1"),
        IPv4Address("10.8.0.2"),
    }

    with pytest.raises(NoAvailableIPAddressError):
        allocator.allocate(
            network=network,
            used_addresses=used,
        )
