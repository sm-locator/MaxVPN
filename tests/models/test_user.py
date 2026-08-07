from tests.factories import make_user


def test_user_has_subscription():
    user = make_user()

    assert user.subscription is not None
    assert user.subscription.valid is True


def test_user_without_subscription():
    user = make_user(subscription=None)

    assert user.subscription is None
