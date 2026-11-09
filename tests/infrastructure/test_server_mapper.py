from backend.infrastructure.database.mappers.server_mapper import ServerMapper
from backend.infrastructure.database.models.server_model import ServerModel
from tests.factories import make_server


def test_mapper_converts_model_to_domain():
    model = ServerModel(
        id=1,
        name="Warsaw",
        country="PL",
        city="Warsaw",
        endpoint="1.1.1.1:51820",
        online=True,
        maintenance=False,
        load=10,
        latency=20,
        max_load=80,
        max_devices=1000,
    )

    server = ServerMapper.to_domain(model)

    assert server.id == model.id
    assert server.endpoint == model.endpoint
    assert server.load == model.load


def test_mapper_converts_domain_to_model():
    server = make_server()

    model = ServerMapper.to_model(server)

    assert model.id == server.id
    assert model.endpoint == server.endpoint
    assert model.load == server.load
