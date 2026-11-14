from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.services.smart_routing_dns_domain_state import (
    SmartRoutingDnsDomainState,
)
from sqlalchemy import delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from app.models.smart_routing_dns_state import (
    SmartRoutingDnsDomainStateRecord,
    SmartRoutingDnsIpSetOutboxRecord,
)


@dataclass(frozen=True, slots=True)
class SmartRoutingDnsIpSetOutboxOperation:
    address_family: str
    address: str
    desired_present: bool


class SmartRoutingDnsStateRepository:
    """Persists DNS ownership and desired ipset mutations transactionally."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def load_domain_states(self) -> tuple[SmartRoutingDnsDomainState, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(SmartRoutingDnsDomainStateRecord).order_by(
                    SmartRoutingDnsDomainStateRecord.domain.asc()
                )
            ).all()
            return tuple(
                SmartRoutingDnsDomainState(
                    domain=record.domain,
                    ipv4_addresses=tuple(record.ipv4_addresses or ()),
                    ipv6_addresses=tuple(record.ipv6_addresses or ()),
                )
                for record in records
            )

    def persist_snapshot_and_enqueue(
        self,
        *,
        domain_states: tuple[SmartRoutingDnsDomainState, ...],
        added_ipv4_addresses: tuple[str, ...] = (),
        removed_ipv4_addresses: tuple[str, ...] = (),
        added_ipv6_addresses: tuple[str, ...] = (),
        removed_ipv6_addresses: tuple[str, ...] = (),
    ) -> None:
        """Commit the ownership snapshot and resulting ipset intent atomically."""
        desired = {state.domain: state for state in domain_states}

        with self._session_factory() as session:
            existing_records = session.scalars(
                select(SmartRoutingDnsDomainStateRecord)
            ).all()
            existing = {record.domain: record for record in existing_records}

            for domain, record in existing.items():
                if domain not in desired:
                    session.delete(record)

            for domain, state in desired.items():
                record = existing.get(domain)
                if record is None:
                    record = SmartRoutingDnsDomainStateRecord(domain=domain)
                    session.add(record)
                record.ipv4_addresses = list(state.ipv4_addresses)
                record.ipv6_addresses = list(state.ipv6_addresses)

            operations = (
                *(("ipv4", address, True) for address in added_ipv4_addresses),
                *(("ipv6", address, True) for address in added_ipv6_addresses),
                *(("ipv4", address, False) for address in removed_ipv4_addresses),
                *(("ipv6", address, False) for address in removed_ipv6_addresses),
            )
            self._upsert_operations(session, operations)
            session.commit()

    def enqueue_present_addresses(
        self,
        ipv4_addresses: tuple[str, ...] = (),
        ipv6_addresses: tuple[str, ...] = (),
    ) -> None:
        operations = (
            *(("ipv4", address, True) for address in ipv4_addresses),
            *(("ipv6", address, True) for address in ipv6_addresses),
        )
        if not operations:
            return
        with self._session_factory() as session:
            self._upsert_operations(session, operations)
            session.commit()

    @staticmethod
    def _upsert_operations(
        session: Session,
        operations: tuple[tuple[str, str, bool], ...],
    ) -> None:
        for address_family, address, desired_present in operations:
            statement = postgresql_insert(SmartRoutingDnsIpSetOutboxRecord).values(
                address_family=address_family,
                address=address,
                desired_present=desired_present,
            )
            statement = statement.on_conflict_do_update(
                constraint="uq_smart_routing_dns_ipset_outbox_family_address",
                set_={
                    "desired_present": statement.excluded.desired_present,
                    "updated_at": func.now(),
                },
            )
            session.execute(statement)

    def list_pending_operations(
        self,
    ) -> tuple[SmartRoutingDnsIpSetOutboxOperation, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(SmartRoutingDnsIpSetOutboxRecord).order_by(
                    desc(SmartRoutingDnsIpSetOutboxRecord.desired_present),
                    SmartRoutingDnsIpSetOutboxRecord.id.asc(),
                )
            ).all()
            return tuple(
                SmartRoutingDnsIpSetOutboxOperation(
                    address_family=record.address_family,
                    address=record.address,
                    desired_present=record.desired_present,
                )
                for record in records
            )

    def acknowledge_operation(
        self,
        operation: SmartRoutingDnsIpSetOutboxOperation,
    ) -> bool:
        """Delete only the exact intent that was executed, not a newer replacement."""
        with self._session_factory() as session:
            result = session.execute(
                delete(SmartRoutingDnsIpSetOutboxRecord).where(
                    SmartRoutingDnsIpSetOutboxRecord.address_family
                    == operation.address_family,
                    SmartRoutingDnsIpSetOutboxRecord.address == operation.address,
                    SmartRoutingDnsIpSetOutboxRecord.desired_present
                    == operation.desired_present,
                )
            )
            session.commit()
            return bool(result.rowcount)
