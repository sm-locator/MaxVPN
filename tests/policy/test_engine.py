from backend.policy.codes import PolicyCode
from backend.policy.registry import PolicyRegistry
from backend.policy.base import Policy
from backend.policy.context import PolicyContext
from backend.policy.engine import PolicyEngine
from backend.policy.result import PolicyResult

from tests.factories import make_device, make_user


class DenyPolicy(Policy):
    def check(self, context: PolicyContext) -> PolicyResult:
        return PolicyResult.deny(
            code=PolicyCode.TEST_DENY,
            message="Denied by test policy",
        )


def test_engine_stops_on_first_denied_policy():
    engine = PolicyEngine([DenyPolicy()])

    context = PolicyContext(
        user=make_user(),
        device=make_device(
            active=True,
            trusted=True,
        ),
    )

    result = engine.execute(context)

    assert result.allowed is False
    assert result.code == PolicyCode.TEST_DENY


def test_default_policy_pipeline_allows_request():
    """
    The default policy pipeline should allow a request
    when all policies return PolicyResult.allow().
    """

    engine = PolicyRegistry.create_default()

    context = PolicyContext(
        user=make_user(),
        device=make_device(
            active=True,
            trusted=True,
        ),
    )

    result = engine.execute(context)

    assert result.allowed is True
    assert result.code == PolicyCode.OK
