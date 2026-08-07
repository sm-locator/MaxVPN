from backend.policy.codes import PolicyCode
from backend.policy.result import PolicyResult


def test_allow():
    result = PolicyResult.allow()

    assert result.allowed is True
    assert result.code == PolicyCode.OK
    assert result.message == ""


def test_deny():
    result = PolicyResult.deny(
        code=PolicyCode.USER_DISABLED,
        message="User is disabled",
    )

    assert result.allowed is False
    assert result.code == PolicyCode.USER_DISABLED
    assert result.message == "User is disabled"
