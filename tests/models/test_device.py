from tests.factories import make_device


def test_device_is_active():
    device = make_device()

    assert device.active is True


def test_device_can_be_disabled():
    device = make_device(active=False)

    assert device.active is False


def test_device_can_be_trusted():
    device = make_device(trusted=True)

    assert device.trusted is True
