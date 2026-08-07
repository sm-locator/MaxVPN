from backend.policy.codes import PolicyCode
from backend.policy.context import PolicyContext
from backend.policy.rules.devices import DevicePolicy

from tests.factories import make_device


def test_device_policy_allows_valid_device():
    policy = DevicePolicy()

    context = PolicyContext(
        device=make_device(
            active=True,
            trusted=True,
        )
    )

    result = policy.check(context)

    assert result.allowed is True
    assert result.code == PolicyCode.OK


def test_device_policy_denies_missing_device():
    policy = DevicePolicy()

    context = PolicyContext(device=None)

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.DEVICE_NOT_FOUND


def test_device_policy_denies_disabled_device():
    policy = DevicePolicy()

    context = PolicyContext(
        device=make_device(
            active=False,
            trusted=True,
        )
    )

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.DEVICE_DISABLED


def test_device_policy_denies_untrusted_device():
    policy = DevicePolicy()

    context = PolicyContext(
        device=make_device(
            active=True,
            trusted=False,
        )
    )

    result = policy.check(context)

    assert result.allowed is False
    assert result.code == PolicyCode.DEVICE_UNTRUSTED
