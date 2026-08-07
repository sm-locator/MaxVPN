from backend.policy.codes import PolicyCode
from backend.policy.context import PolicyContext
from backend.policy.rules.load import LoadPolicy
from tests.factories import make_server


def test_load_policy_allows_low_load():
    policy = LoadPolicy()

    context = PolicyContext(
        server=make_server(load=20, max_load=80),
    )

    result = policy.check(context)

    assert result.allowed is True


def test_load_policy_allows_load_below_limit():
    policy = LoadPolicy()

    context = PolicyContext(
        server=make_server(load=79, max_load=80),
    )

    result = policy.check(context)

    assert result.allowed is True


def test_load_policy_denies_server_at_limit():
    policy = LoadPolicy()

    context = PolicyContext(
        server=make_server(load=80, max_load=80),
    )

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.SERVER_OVERLOADED


def test_load_policy_denies_overloaded_server():
    policy = LoadPolicy()

    context = PolicyContext(
        server=make_server(load=95, max_load=80),
    )

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.SERVER_OVERLOADED


def test_load_policy_allows_missing_server():
    policy = LoadPolicy()

    context = PolicyContext(server=None)

    result = policy.check(context)

    assert result.allowed is True
