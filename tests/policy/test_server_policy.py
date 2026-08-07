from backend.policy.codes import PolicyCode
from backend.policy.context import PolicyContext
from backend.policy.rules.server import ServerPolicy
from tests.factories import make_server


def test_server_policy_allows_online_server():
    policy = ServerPolicy()

    context = PolicyContext(
        server=make_server(),
    )

    result = policy.check(context)

    assert result.allowed is True


def test_server_policy_denies_missing_server():
    policy = ServerPolicy()

    context = PolicyContext(server=None)

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.SERVER_UNAVAILABLE


def test_server_policy_denies_offline_server():
    policy = ServerPolicy()

    context = PolicyContext(
        server=make_server(online=False),
    )

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.SERVER_OFFLINE


def test_server_policy_denies_server_on_maintenance():
    policy = ServerPolicy()

    context = PolicyContext(
        server=make_server(maintenance=True),
    )

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.SERVER_MAINTENANCE
