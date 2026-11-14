from unittest.mock import patch

import pytest
from backend.services.domain_routing_resolver import (
    DomainRoutingResolutionError,
    DomainRoutingResolver,
)


def test_resolve_normalizes_domain_and_returns_unique_addresses() -> None:
    resolver = DomainRoutingResolver()

    results = [
        (
            2,
            1,
            6,
            "",
            ("192.0.2.10", 0),
        ),
        (
            10,
            1,
            6,
            "",
            ("2001:db8::10", 0, 0, 0),
        ),
        (
            2,
            1,
            6,
            "",
            ("192.0.2.10", 0),
        ),
    ]

    with patch(
        "backend.services.domain_routing_resolver.socket.getaddrinfo",
        return_value=results,
    ) as mocked:
        addresses = resolver.resolve("  Example.COM. ")

    mocked.assert_called_once_with(
        "example.com",
        None,
        0,
        1,
    )

    assert addresses == (
        "192.0.2.10",
        "2001:db8::10",
    )


def test_resolve_rejects_dns_failure() -> None:
    resolver = DomainRoutingResolver()

    with patch(
        "backend.services.domain_routing_resolver.socket.getaddrinfo",
        side_effect=__import__("socket").gaierror("temporary failure"),
    ):
        with pytest.raises(
            DomainRoutingResolutionError,
            match="failed to resolve domain",
        ):
            resolver.resolve("example.com")


def test_resolve_rejects_empty_result() -> None:
    resolver = DomainRoutingResolver()

    with patch(
        "backend.services.domain_routing_resolver.socket.getaddrinfo",
        return_value=[],
    ):
        with pytest.raises(
            DomainRoutingResolutionError,
            match="resolved to no addresses",
        ):
            resolver.resolve("example.com")
