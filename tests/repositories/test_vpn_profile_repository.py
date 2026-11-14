from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import BaseModel
from app.models.user import User
from app.models.vpn_profile import VpnProfile
from app.repositories.vpn_profile import VpnProfileRepository


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")

    BaseModel.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            VpnProfile.__table__,
        ],
    )

    return Session(engine)


def test_get_by_user_returns_profile() -> None:
    db = make_session()

    user = User(
        email="user@example.com",
        password_hash="hash",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = VpnProfile(
        user_id=user.id,
        name="Primary VPN",
        enabled=True,
        encrypted_provider_config="encrypted-data",
    )
    db.add(profile)
    db.commit()

    repository = VpnProfileRepository(db)

    result = repository.get_by_user(user.id)

    assert result is not None
    assert result.id == profile.id
    assert result.user_id == user.id
    assert result.name == "Primary VPN"
    assert result.enabled is True
    assert result.encrypted_provider_config == "encrypted-data"


def test_get_by_user_returns_none_when_missing() -> None:
    db = make_session()

    repository = VpnProfileRepository(db)

    assert repository.get_by_user(999) is None


def test_create_for_user_persists_profile() -> None:
    db = make_session()

    user = User(
        email="creator@example.com",
        password_hash="hash",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    repository = VpnProfileRepository(db)

    profile = repository.create_for_user(
        user_id=user.id,
        name="Primary VPN",
        encrypted_provider_config="encrypted-data",
    )

    assert profile.id is not None
    assert profile.user_id == user.id
    assert profile.name == "Primary VPN"
    assert profile.enabled is True


def test_create_for_user_can_disable_profile() -> None:
    db = make_session()

    user = User(
        email="disabled@example.com",
        password_hash="hash",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    repository = VpnProfileRepository(db)

    profile = repository.create_for_user(
        user_id=user.id,
        name="Disabled VPN",
        encrypted_provider_config="encrypted-data",
        enabled=False,
    )

    assert profile.enabled is False


def test_repository_does_not_return_other_users_profile() -> None:
    db = make_session()

    user_one = User(
        email="one@example.com",
        password_hash="hash",
        role="user",
    )
    user_two = User(
        email="two@example.com",
        password_hash="hash",
        role="user",
    )

    db.add_all([user_one, user_two])
    db.commit()
    db.refresh(user_one)
    db.refresh(user_two)

    profile = VpnProfile(
        user_id=user_one.id,
        name="Private VPN",
        enabled=True,
        encrypted_provider_config="encrypted-data",
    )
    db.add(profile)
    db.commit()

    repository = VpnProfileRepository(db)

    assert repository.get_by_user(user_two.id) is None


def test_user_relationship_returns_profile() -> None:
    db = make_session()

    user = User(
        email="relationship@example.com",
        password_hash="hash",
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = VpnProfile(
        user_id=user.id,
        name="Primary VPN",
        enabled=True,
        encrypted_provider_config="encrypted-data",
    )
    db.add(profile)
    db.commit()

    db.refresh(user)

    assert user.vpn_profile is not None
    assert user.vpn_profile.id == profile.id
