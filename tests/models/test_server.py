from tests.factories import make_server


def test_server_is_online():
    server = make_server()

    assert server.online is True


def test_server_can_be_offline():
    server = make_server(online=False)

    assert server.online is False


def test_server_has_load():
    server = make_server(load=73)

    assert server.load == 73
