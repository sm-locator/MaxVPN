from backend.application.use_cases.create_client import CreateClientUseCase
from backend.application.use_cases.select_best_server import (
    SelectBestServerUseCase,
)
from backend.policy.registry import PolicyRegistry
from backend.services.routing_service import RoutingService
from backend.services.in_memory_server_repository import (
    InMemoryServerRepository,
)
from backend.services.server_selector import ServerSelector
from backend.services.static_address_allocator import (
    StaticAddressAllocator,
)
from backend.services.static_key_provider import StaticKeyProvider
from tests.factories import make_context, make_server


def test_create_client_returns_client_config():
    repository = InMemoryServerRepository(
        [
            make_server(id=1, load=20),
        ]
    )

    routing = RoutingService(
        repository,
        ServerSelector(),
        PolicyRegistry.create_default(),
    )

    select_server = SelectBestServerUseCase(routing)

    use_case = CreateClientUseCase(
        select_server=select_server,
        key_provider=StaticKeyProvider(),
        address_allocator=StaticAddressAllocator(),
    )

    config = use_case.execute(make_context())

    assert config is not None
    assert config.server.id == 1
    assert config.key_pair.private_key == "private-key"
    assert config.tunnel.address == "10.100.0.2/32"
    assert config.peer.public_key == config.server.public_key
