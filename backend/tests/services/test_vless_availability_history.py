from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.vless_profile_service import VlessProfileService


class FakeAvailabilityRepository:
    def __init__(self):
        self.records = [
            SimpleNamespace(
                id=1,
                user_id=7,
                last_delay_ms=None,
                last_checked_at=None,
                last_success_at=None,
                first_failed_at=None,
                last_outage_started_at=None,
                last_recovered_at=None,
                last_outage_duration_seconds=None,
                consecutive_failures=0,
            )
        ]
        self.update_calls = 0

    def list_by_user(self, user_id):
        return [record for record in self.records if record.user_id == user_id]

    def update_many(self, records):
        self.update_calls += 1
        return records


def make_service():
    service = object.__new__(VlessProfileService)
    service._repository = FakeAvailabilityRepository()
    return service


def test_outage_duration_persists_across_repeated_failures_and_recovery():
    service = make_service()
    started = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)

    first = service.record_delay_results(7, {1: None}, checked_at=started)[0]
    assert first["reachable"] is False
    assert first["first_failed_at"] == "2026-10-20T10:00:00Z"
    assert first["unavailable_seconds"] == 0
    assert first["consecutive_failures"] == 1

    second = service.record_delay_results(
        7, {1: None}, checked_at=started + timedelta(seconds=125)
    )[0]
    assert second["first_failed_at"] == first["first_failed_at"]
    assert second["unavailable_seconds"] == 125
    assert second["consecutive_failures"] == 2

    recovered_at = started + timedelta(seconds=305)
    recovered = service.record_delay_results(7, {1: 143}, checked_at=recovered_at)[0]
    assert recovered["reachable"] is True
    assert recovered["delay_ms"] == 143
    assert recovered["first_failed_at"] is None
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_success_at"] == "2026-10-20T10:05:05Z"
    assert recovered["last_outage_started_at"] == "2026-10-20T10:00:00Z"
    assert recovered["last_recovered_at"] == "2026-10-20T10:05:05Z"
    assert recovered["last_outage_duration_seconds"] == 305


def test_history_read_does_not_trigger_probe_and_returns_existing_state():
    service = make_service()
    checked = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
    service.record_delay_results(7, {1: None}, checked_at=checked)

    history = service.get_delay_history(7)

    assert len(history) == 1
    assert history[0]["profile_id"] == 1
    assert history[0]["consecutive_failures"] == 1
    assert history[0]["first_failed_at"] == "2026-10-20T10:00:00Z"
