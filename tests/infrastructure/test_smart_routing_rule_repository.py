import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "backend"),
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models.smart_routing_rule import SmartRoutingRule
from app.models.user import User
from app.repositories.smart_routing_rule import SmartRoutingRuleRepository


def make_session():
    engine = create_engine("sqlite:///:memory:")

    Base.metadata.tables["users"].create(engine)
    Base.metadata.tables["smart_routing_rules"].create(engine)

    session_factory = sessionmaker(bind=engine)
    return session_factory()


def make_users(session) -> None:
    session.execute(
        User.__table__.insert(),
        [
            {
                "id": 1,
                "email": "user1@example.com",
                "password_hash": "hash1",
                "role": "user",
            },
            {
                "id": 2,
                "email": "user2@example.com",
                "password_hash": "hash2",
                "role": "user",
            },
        ],
    )
    session.commit()


def make_rule(
    *,
    user_id: int,
    priority: int,
    target: str,
) -> SmartRoutingRule:
    return SmartRoutingRule(
        user_id=user_id,
        target_type="cidr",
        target=target,
        action="direct",
        priority=priority,
        address_family="ipv4",
        enabled=True,
    )


def test_get_by_user_returns_only_user_rules_in_priority_order() -> None:
    session = make_session()
    make_users(session)
    repository = SmartRoutingRuleRepository(session)

    first = make_rule(
        user_id=1,
        priority=200,
        target="2.2.2.0/24",
    )
    second = make_rule(
        user_id=1,
        priority=100,
        target="1.1.1.0/24",
    )
    foreign = make_rule(
        user_id=2,
        priority=50,
        target="3.3.3.0/24",
    )

    session.add_all([first, second, foreign])
    session.commit()

    rules = repository.get_by_user(1)

    assert [rule.priority for rule in rules] == [100, 200]
    assert [rule.target for rule in rules] == [
        "1.1.1.0/24",
        "2.2.2.0/24",
    ]


def test_get_by_id_cannot_return_foreign_user_rule() -> None:
    session = make_session()
    make_users(session)
    repository = SmartRoutingRuleRepository(session)

    rule = make_rule(
        user_id=1,
        priority=100,
        target="1.1.1.0/24",
    )

    session.add(rule)
    session.commit()

    assert rule.id is not None

    assert repository.get_by_id(1, rule.id) is rule
    assert repository.get_by_id(2, rule.id) is None


def test_create_uses_base_repository() -> None:
    session = make_session()
    repository = SmartRoutingRuleRepository(session)

    rule = repository.create(
        make_rule(
            user_id=1,
            priority=100,
            target="1.1.1.0/24",
        )
    )

    assert rule.id is not None
    assert repository.get(rule.id) is rule
