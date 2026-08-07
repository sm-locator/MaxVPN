from backend.application.use_cases.select_best_server import (
    SelectBestServerUseCase,
)
from backend.policy.registry import PolicyRegistry
from backend.services.routing_service import RoutingService
from backend.services.server_repository import ServerRepository
from backend.services.server_selector import ServerSelector
from tests.factories import make_context, make_server


def test_use_case_returns_best_server():
    repository = ServerRepository(
        [
            make_server(id=1, load=60),
            make_server(id=2, load=20),
            make_server(id=3, load=40),
        ]
    )

    routing = RoutingService(
        repository,
        ServerSelector(),
        PolicyRegistry.create_default(),
    )

    use_case = SelectBestServerUseCase(routing)

    server = use_case.execute(make_context())

    assert server is not None
    assert server.id == 2
