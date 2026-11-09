from backend.policy.context import PolicyContext
from backend.policy.registry import PolicyRegistry
from backend.services.routing_service import RoutingService
from backend.services.in_memory_server_repository import (
    InMemoryServerRepository,
)
from backend.services.server_selector import ServerSelector
from tests.factories import make_context, make_device, make_server, make_user


def test_routing_service_selects_lowest_loaded_server():
    repository = InMemoryServerRepository(
        [
            make_server(id=1, load=70),
            make_server(id=2, load=20),
            make_server(id=3, load=40),
        ]
    )

    service = RoutingService(
        repository,
        ServerSelector(),
        PolicyRegistry.create_default(),
    )

    context = PolicyContext(
        user=make_user(),
        device=make_device(),
    )

    server = service.select(context)

    assert server.id == 2


def test_routing_service_skips_overloaded_servers():
    repository = InMemoryServerRepository(
        [
            make_server(id=1, load=95, max_load=80),
            make_server(id=2, load=40, max_load=80),
            make_server(id=3, load=60, max_load=80),
        ]
    )

    service = RoutingService(
        repository,
        ServerSelector(),
        PolicyRegistry.create_default(),
    )

    context = make_context()

    server = service.select(context)

    assert server is not None
    assert server.id == 2


def test_routing_service_returns_none_when_all_servers_are_overloaded():
    repository = InMemoryServerRepository(
        [
            make_server(id=1, load=95, max_load=80),
            make_server(id=2, load=90, max_load=80),
        ]
    )

    service = RoutingService(
        repository,
        ServerSelector(),
        PolicyRegistry.create_default(),
    )

    context = make_context()

    server = service.select(context)

    assert server is None
