from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vless_control as vc


def _availability_snapshot(epoch, samples):
    return {
        "selection_mode": "auto",
        "active_outbound": "vless-profile-1",
        "observed_at_epoch": epoch,
        "profile_delays": samples,
        "urltest_interval": "3m",
    }


@pytest.fixture
def probes(tmp_path, monkeypatch):
    monkeypatch.setattr(vc, "DELAY_HISTORY_FILE", tmp_path / "manual.json")
    c = vc.VlessControl(tmp_path / "profiles.json", tmp_path / "config.json")
    c._save_store({"profiles": [{"id": 1, "enabled": True}]}, backup=False)
    monkeypatch.setattr(c, "_running", lambda: True)
    base = datetime(2026, 11, 1, tzinfo=timezone.utc)

    def stamp(n):
        return vc._timestamp_iso(base + timedelta(seconds=n))

    def manual(n, delay):
        monkeypatch.setattr(vc, "_utc_now", lambda: base + timedelta(seconds=n))
        body = '{"delay":%s}\n200' % delay if delay else "{}\n504"
        monkeypatch.setattr(
            c, "_exec", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=body)
        )
        return c.test_delays()

    def auto(n, delay, empty=False):
        sample = {
            "observed_at": None if empty else stamp(n),
            "delay_ms": delay,
            "failed": delay is None and not empty,
        }
        snap = _availability_snapshot(base.timestamp() + n, {"vless-profile-1": sample})
        c.record_selection_observation(snap)

    return c, stamp, manual, auto


def test_first_failure_after_latest_success_across_sources_and_restart(probes):
    c, stamp, manual, auto = probes
    manual(0, None)
    auto(10, 21)
    auto(20, None)
    manual(35, None)
    auto(55, None)
    auto(55, None)
    auto(60, None, empty=True)
    restarted = vc.VlessControl(c.profile_file, c.config_file)

    def history():
        return restarted.get_selection_history()["profile_availability"]["1"]

    item = history()
    assert (item["first_failed_at"], item["last_checked_at"]) == (stamp(20), stamp(55))
    assert item["last_success_at"] == stamp(10)
    # A late success splits the active outage. Its first remaining failure can
    # be neither the first nor the latest failure of either independent source.
    auto(30, 40)
    assert history()["first_failed_at"] == stamp(35)
    manual(65, 70)
    item = history()
    assert item["first_failed_at"] is None
    assert item["last_recovered_at"] == stamp(65)
    assert item["last_outage_duration_seconds"] == 30
    auto(55, None)
    assert history()["source"] == "manual"
    assert history()["first_failed_at"] is None


@pytest.mark.parametrize(
    "rc,body",
    [
        (7, ""),
        (28, ""),
        (0, "{}\n404"),
        (0, "{}\n200"),
        (0, '{"delay":true}\n200'),
        (0, "invalid\n500"),
    ],
)
def test_unknown_probe_leaves_existing_outage_unchanged(probes, monkeypatch, rc, body):
    c, stamp, manual, _ = probes
    manual(0, None)
    monkeypatch.setattr(
        c, "_exec", lambda *a, **kw: SimpleNamespace(returncode=rc, stdout=body)
    )
    result = c.test_delays()
    assert result["unknown"] == 1 and not result["results"]
    assert c.get_delay_history()["results"][0]["consecutive_failures"] == 1
    item = c.get_selection_history()["profile_availability"]["1"]
    assert item["last_checked_at"] == item["first_failed_at"] == stamp(0)


def test_empty_history_is_confirmed_at_configured_interval(probes, monkeypatch):
    c, stamp, manual, _ = probes
    manual(0, 18)

    def snapshot():
        return _availability_snapshot(
            1800000000, {"vless-profile-1": {"observed_at": None, "delay_ms": None}}
        )

    responses = iter([(0, "{}\n503"), (0, '{"delay":42}\n200')])
    times = iter([100, 120, 400])
    # Only the probe scheduler uses these values.
    clock = {"now": 100}
    monkeypatch.setattr(vc.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        c,
        "_exec",
        lambda *a, **kw: SimpleNamespace(
            **dict(zip(("returncode", "stdout"), next(responses)))
        ),
    )
    for offset, expected in [(10, "no_result"), (20, "no_result"), (30, "reachable")]:
        clock["now"] = next(times)
        monkeypatch.setattr(
            vc, "_utc_now", lambda: vc._timestamp_datetime(stamp(offset))
        )
        c.poll_selection(snapshot)
        item = c.get_selection_history()["profile_availability"]["1"]
        assert item["status"] == expected
        if offset != 30:
            assert item["first_failed_at"] == stamp(10)
    assert item["last_recovered_at"] == stamp(30)


def test_multiple_clash_history_entries_are_merged_in_measurement_order(probes, monkeypatch):
    monkeypatch.setenv("MAXVPN_APPLIANCE_ROOT", str(probes[0].profile_file.parent))
    from appliance.maxvpn.server import _selection_latest_delay

    c, stamp, manual, _ = probes
    manual(10, None)
    sample = _selection_latest_delay(
        {
            "history": [
                {"time": stamp(80), "delay": 0},
                {"time": stamp(70), "delay": 0},
                {"time": stamp(60), "delay": 17},
                {"time": stamp(90)},
                {"time": stamp(95), "delay": False},
            ]
        }
    )
    assert sample["observed_at"] == stamp(80)
    c.record_selection_observation(
        _availability_snapshot(1800000000, {"vless-profile-1": sample})
    )
    item = c.get_selection_history()["profile_availability"]["1"]
    assert item["first_failed_at"] == stamp(70)
    assert item["last_checked_at"] == stamp(80)


def test_compaction_retains_open_outage_evidence_and_completed_bounds(probes):
    from contextlib import closing

    c, stamp, _, auto = probes
    for n, delay in enumerate([None, None, None, 40, 41, 42, None, None, None, None]):
        auto(n, delay)
    with closing(c._availability_connection({})) as db, db:
        c._compact_availability(db, vc._timestamp_datetime(stamp(100)))
    item = c.get_selection_history()["profile_availability"]["1"]
    assert item["last_recovered_at"] == stamp(3)
    assert item["last_outage_duration_seconds"] == 3
    assert item["first_failed_at"] == stamp(6)
    auto(7, 25)
    assert c.get_selection_history()["profile_availability"]["1"][
        "first_failed_at"
    ] == stamp(8)


def test_upgrade_uses_only_confirmed_events_and_preserves_previous_recovery(probes):
    import json

    c, stamp, _, _ = probes
    vc.DELAY_HISTORY_FILE.write_text(
        json.dumps(
            {
                "profiles": {
                    "1": {
                        "last_checked_at": stamp(80),
                        "first_failed_at": stamp(70),
                        "last_outage_started_at": stamp(70),
                        "last_success_at": stamp(50),
                        "last_recovered_at": stamp(50),
                        "last_outage_duration_seconds": 30,
                    }
                }
            }
        )
    )
    c.selection_history_file.write_text(
        json.dumps(
            {
                "profile_availability": {
                    "1": {
                        "reason": "successful_history_disappeared",
                        "first_missing_at": stamp(55),
                    }
                }
            }
        )
    )
    item = c.get_selection_history()["profile_availability"]["1"]
    assert item["first_failed_at"] == stamp(70)
    assert item["last_outage_duration_seconds"] == 30
