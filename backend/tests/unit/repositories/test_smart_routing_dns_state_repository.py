from types import SimpleNamespace
from unittest.mock import Mock

from backend.services.smart_routing_dns_domain_state import SmartRoutingDnsDomainState

from app.models.smart_routing_dns_state import (
    SmartRoutingDnsDomainStateRecord,
)
from app.repositories.smart_routing_dns_state import (
    SmartRoutingDnsIpSetOutboxOperation,
    SmartRoutingDnsStateRepository,
)


class SessionContext:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, traceback):
        return False


def make_repository(session):
    return SmartRoutingDnsStateRepository(lambda: SessionContext(session))


def test_load_domain_states_maps_orm_records_to_service_values():
    session = Mock()
    session.scalars.return_value.all.return_value = [
        SmartRoutingDnsDomainStateRecord(
            domain="example.com",
            ipv4_addresses=["192.0.2.10"],
            ipv6_addresses=["2001:db8::10"],
        )
    ]

    result = make_repository(session).load_domain_states()

    assert result == (
        SmartRoutingDnsDomainState(
            "example.com",
            ("192.0.2.10",),
            ("2001:db8::10",),
        ),
    )


def test_persist_snapshot_and_enqueue_commits_domain_and_outbox_in_one_session():
    session = Mock()
    session.scalars.return_value.all.return_value = []
    repository = make_repository(session)

    repository.persist_snapshot_and_enqueue(
        domain_states=(SmartRoutingDnsDomainState("example.com", ("192.0.2.10",)),),
        added_ipv4_addresses=("192.0.2.10",),
        removed_ipv6_addresses=("2001:db8::10",),
    )

    session.add.assert_called_once()
    assert session.execute.call_count == 2
    session.commit.assert_called_once()
    inserted_domain = session.add.call_args.args[0]
    assert inserted_domain.domain == "example.com"
    assert inserted_domain.ipv4_addresses == ["192.0.2.10"]


def test_list_pending_operations_returns_adds_before_deletes():
    session = Mock()
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(
            address_family="ipv4",
            address="192.0.2.1",
            desired_present=True,
        ),
        SimpleNamespace(
            address_family="ipv4",
            address="192.0.2.2",
            desired_present=False,
        ),
    ]

    operations = make_repository(session).list_pending_operations()

    assert operations == (
        SmartRoutingDnsIpSetOutboxOperation("ipv4", "192.0.2.1", True),
        SmartRoutingDnsIpSetOutboxOperation("ipv4", "192.0.2.2", False),
    )


def test_acknowledge_operation_deletes_only_matching_desired_state():
    session = Mock()
    session.execute.return_value.rowcount = 1
    operation = SmartRoutingDnsIpSetOutboxOperation("ipv4", "192.0.2.10", False)

    acknowledged = make_repository(session).acknowledge_operation(operation)

    assert acknowledged is True
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "address_family" in compiled
    assert "desired_present" in compiled
    session.commit.assert_called_once()
