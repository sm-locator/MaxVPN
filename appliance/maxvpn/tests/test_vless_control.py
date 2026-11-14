import json
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

import vless_control  # noqa: E402
from vless_control import (  # noqa: E402
    VlessControl,
    VlessControlError,
    _parse_happ_json,
    _parse_vless_uri,
    _render_config,
)

TEST_UUID = "123e4567-e89b-42d3-a456-426614174000"
TEST_UUID_2 = "123e4567-e89b-42d3-a456-426614174001"
TEST_PBK = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def profile(
    profile_id=1,
    address="node.example.com",
    name="Test node",
    enabled=True,
    uuid=TEST_UUID,
):
    return {
        "id": profile_id,
        "name": name,
        "enabled": enabled,
        "address": address,
        "port": 443,
        "uuid": uuid,
        "flow": "xtls-rprx-vision",
        "network": "tcp",
        "security": "reality",
        "reality": {
            "public_key": TEST_PBK,
            "server_name": "www.example.com",
            "short_id": "abcd",
            "fingerprint": "chrome",
        },
    }


def test_parse_vless_reality_uri():
    uri = (
        f"vless://{TEST_UUID}@node.example.com:443?encryption=none&type=tcp"
        f"&security=reality&sni=www.example.com&fp=chrome&pbk={TEST_PBK}"
        "&sid=abcd&flow=xtls-rprx-vision#Fast%20Node"
    )
    parsed = _parse_vless_uri(uri)
    assert parsed["name"] == "Fast Node"
    assert parsed["address"] == "node.example.com"
    assert parsed["port"] == 443
    assert parsed["reality"]["short_id"] == "abcd"
    assert parsed["uuid"] == TEST_UUID


def test_parse_vless_uri_rejects_unsupported_transport():
    uri = (
        f"vless://{TEST_UUID}@node.example.com:443?encryption=none&type=grpc"
        f"&security=reality&sni=www.example.com&pbk={TEST_PBK}"
    )
    with pytest.raises(ValueError, match="TCP"):
        _parse_vless_uri(uri)


def test_parse_xray_happ_json():
    source = json.dumps(
        {
            "remarks": "Xray node",
            "outbounds": [
                {
                    "protocol": "vless",
                    "tag": "proxy",
                    "settings": {
                        "vnext": [
                            {
                                "address": "node.example.com",
                                "port": 443,
                                "users": [
                                    {"id": TEST_UUID, "flow": "xtls-rprx-vision"}
                                ],
                            }
                        ]
                    },
                    "streamSettings": {
                        "network": "tcp",
                        "security": "reality",
                        "realitySettings": {
                            "publicKey": TEST_PBK,
                            "serverName": "www.example.com",
                            "shortId": "abcd",
                            "fingerprint": "chrome",
                        },
                    },
                }
            ],
        }
    )
    parsed = _parse_happ_json(source)
    assert parsed["name"] == "Xray node"
    assert parsed["reality"]["public_key"] == TEST_PBK
    assert parsed["flow"] == "xtls-rprx-vision"


def test_render_config_builds_urltest_and_manual_selector():
    store = {
        "profiles": [
            profile(),
            profile(2, "second.example.com", "Second", uuid=TEST_UUID_2),
        ],
        "settings": {"urltest_interval": "5m", "urltest_tolerance_ms": 100},
        "selection": {"mode": "manual", "profile_id": 2},
    }
    config = _render_config(store)
    outbounds = {item["tag"]: item for item in config["outbounds"]}
    assert outbounds["vless-auto"]["interval"] == "5m"
    assert outbounds["vless-auto"]["tolerance"] == 100
    assert outbounds["vless-auto"]["url"] == "https://cp.cloudflare.com/generate_204"
    for tag in ("vless-profile-1", "vless-profile-2"):
        # Do not restrict sing-box destination traffic to TCP: urltest needs a
        # UDP-capable outbound as well, even when VLESS transport itself is TCP.
        assert "network" not in outbounds[tag]
        assert outbounds[tag]["packet_encoding"] == "xudp"
    assert outbounds["vless-out"]["default"] == "vless-profile-2"
    assert outbounds["vless-out"]["outbounds"] == [
        "vless-auto",
        "vless-profile-1",
        "vless-profile-2",
    ]
    assert config["inbounds"][0]["interface_name"] == "maxvpn0"
    assert (
        config["experimental"]["clash_api"]["external_controller"] == "127.0.0.1:9090"
    )


def test_render_config_requires_an_enabled_profile():
    with pytest.raises(VlessControlError, match="хотя бы один"):
        _render_config({"profiles": [profile(enabled=False)]})


def test_profile_store_file_is_private_without_changing_parent_permissions(tmp_path):
    parent = tmp_path / "maxvpn"
    parent.mkdir()
    parent.chmod(0o750)
    target = parent / "vless-profiles.json"
    controller = VlessControl(profile_file=target)
    controller._save_store(
        {"version": 1, "profiles": [], "settings": {}, "selection": {}}, backup=False
    )
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(parent.stat().st_mode) == 0o750


def test_import_bundle_adds_profiles_and_preserves_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(vless_control, "CONFIG_FILE", tmp_path / "absent-config.json")
    monkeypatch.setattr(vless_control, "BACKUP_DIR", tmp_path / "vless-backups")
    controller = VlessControl(
        profile_file=tmp_path / "store.json", config_file=tmp_path / "runtime.json"
    )
    bundle = {
        "format": "maxvpn-vless-profiles",
        "version": 1,
        "settings": {"urltest_interval": "5m", "urltest_tolerance_ms": 125},
        "profiles": [
            {
                "id": 7,
                "name": "Node A",
                "enabled": True,
                "source": f"vless://{TEST_UUID}@node.example.com:443?encryption=none&type=tcp&security=reality&sni=www.example.com&pbk={TEST_PBK}&sid=abcd&fp=chrome",
            },
            {
                "id": 8,
                "name": "Node B",
                "enabled": False,
                "source": f"vless://{TEST_UUID_2}@second.example.com:443?encryption=none&type=tcp&security=reality&sni=www.example.com&pbk={TEST_PBK}&sid=abcd&fp=chrome",
            },
        ],
    }
    result = controller.import_profiles(bundle)
    assert result["imported"] == 2
    assert result["failed"] == 0
    saved = json.loads((tmp_path / "store.json").read_text())
    assert saved["settings"]["urltest_interval"] == "5m"
    assert saved["settings"]["urltest_tolerance_ms"] == 125
    assert [item["id"] for item in saved["profiles"]] == [7, 8]
    assert saved["profiles"][1]["enabled"] is False


def test_import_invalid_bundle_does_not_replace_existing_profiles(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(vless_control, "CONFIG_FILE", tmp_path / "absent-config.json")
    store_path = tmp_path / "store.json"
    controller = VlessControl(
        profile_file=store_path, config_file=tmp_path / "runtime.json"
    )
    controller._save_store(
        {
            "version": 1,
            "profiles": [profile()],
            "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
            "selection": {"mode": "auto", "profile_id": None},
        },
        backup=False,
    )
    before = store_path.read_text()
    with pytest.raises(VlessControlError, match="не изменил список"):
        controller.import_profiles({"profiles": [{"source": "not-a-vless-link"}]})
    assert store_path.read_text() == before


class RuntimeRunner:
    def __init__(self, interface_up=True):
        self.interface_up = interface_up

    def __call__(self, args, **_kwargs):
        from subprocess import CompletedProcess

        command = [str(item) for item in args]
        stdout = ""
        if command and command[0] == "ubus":
            stdout = json.dumps(
                {"maxvpn-sing-box": {"instances": {"main": {"running": True}}}}
            )
        elif (
            command
            and command[0] == "curl"
            and command[-1].endswith("/proxies/vless-out")
        ):
            stdout = json.dumps({"now": "vless-auto"})
        elif (
            command
            and command[0] == "curl"
            and command[-1].endswith("/proxies/vless-auto")
        ):
            stdout = json.dumps({"now": "vless-profile-1"})
        elif command and command[0] == "ip":
            flags = (
                "POINTOPOINT,NOARP,UP,LOWER_UP"
                if self.interface_up
                else "POINTOPOINT,NOARP"
            )
            stdout = "3: maxvpn0: <%s> mtu 1380 state UNKNOWN" % flags
        return CompletedProcess(command, 0, stdout=stdout, stderr="")


def test_runtime_status_does_not_mark_vless_healthy_without_tun_interface(
    tmp_path, monkeypatch
):
    binary = tmp_path / "sing-box"
    service = tmp_path / "maxvpn-sing-box"
    binary.write_text("test")
    service.write_text("test")
    monkeypatch.setattr(vless_control, "SING_BOX", binary)
    monkeypatch.setattr(vless_control, "SERVICE", service)
    monkeypatch.setattr(vless_control, "MODE_FILE", tmp_path / "runtime-mode")
    (tmp_path / "runtime-mode").write_text("vless\n")

    config = tmp_path / "runtime.json"
    config.write_text("{}")
    store_file = tmp_path / "profiles.json"
    store_file.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [profile()],
                "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
                "selection": {"mode": "auto", "profile_id": None},
            }
        )
    )
    controller = VlessControl(
        profile_file=store_file,
        config_file=config,
        command_runner=RuntimeRunner(interface_up=False),
    )

    state = controller.get_state()
    assert state["traffic_mode"] == "vless"
    assert state["running"] is True
    assert state["lan_routing_enabled"] is True
    assert state["tun_interface_up"] is False
    assert state["lan_route_healthy"] is False
    assert state["route_health"] == "degraded"


def test_disabling_manually_selected_profile_resets_selection_to_auto(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(vless_control, "CONFIG_FILE", tmp_path / "absent-config.json")
    monkeypatch.setattr(vless_control, "BACKUP_DIR", tmp_path / "vless-backups")
    store_file = tmp_path / "profiles.json"
    store_file.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    profile(),
                    profile(2, "second.example.com", "Second", uuid=TEST_UUID_2),
                ],
                "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
                "selection": {"mode": "manual", "profile_id": 1},
            }
        )
    )
    controller = VlessControl(
        profile_file=store_file, config_file=tmp_path / "runtime.json"
    )

    controller.update_profile(1, {"enabled": False})
    saved = json.loads(store_file.read_text())
    assert saved["selection"] == {"mode": "auto", "profile_id": None}


def test_failed_start_from_stopped_vless_mode_restores_config_and_requests_wan(
    tmp_path, monkeypatch
):
    from subprocess import CompletedProcess

    binary = tmp_path / "sing-box"
    service = tmp_path / "maxvpn-sing-box"
    binary.write_text("test")
    service.write_text("test")
    binary.chmod(0o755)
    service.chmod(0o755)
    mode_file = tmp_path / "runtime-mode"
    mode_file.write_text("vless\n")
    config_file = tmp_path / "sing-box-vless.json"
    old_config = '{"old_config":true}\n'
    config_file.write_text(old_config)
    profile_file = tmp_path / "profiles.json"
    profile_file.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [profile()],
                "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
                "selection": {"mode": "auto", "profile_id": None},
            }
        )
    )
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(vless_control, "SING_BOX", binary)
    monkeypatch.setattr(vless_control, "SERVICE", service)
    monkeypatch.setattr(vless_control, "MODE_FILE", mode_file)
    monkeypatch.setattr(vless_control, "BACKUP_DIR", backup_dir)

    class FailStartController(VlessControl):
        def __init__(self):
            self.wan_requested = False
            self.vless_route_requested = False
            super().__init__(
                profile_file=profile_file,
                config_file=config_file,
                command_runner=self.runner,
            )

        def _running(self):
            return False

        def runner(self, args, **_kwargs):
            command = [str(item) for item in args]
            if command[0] == str(binary) and "check" in command:
                return CompletedProcess(command, 0, stdout="", stderr="")
            if (
                command[0] == str(service)
                and len(command) > 1
                and command[1] == "start"
            ):
                return CompletedProcess(
                    command, 1, stdout="", stderr="synthetic start failure"
                )
            if command == ["/usr/bin/vpn-lan-off"]:
                self.wan_requested = True
                mode_file.write_text("wan\n")
            if command == ["/usr/bin/vpn-lan-vless-on"]:
                self.vless_route_requested = True
                mode_file.write_text("vless\n")
            return CompletedProcess(command, 0, stdout="", stderr="")

    controller = FailStartController()
    with pytest.raises(VlessControlError, match="Откат конфигурации не подтверждён"):
        controller.apply_config(start=True)

    assert config_file.read_text() == old_config
    assert controller.vless_route_requested is True
    assert controller.wan_requested is False
    assert mode_file.read_text().strip() == "vless"


def test_delay_history_persists_outage_age_and_resets_after_recovery(
    tmp_path, monkeypatch
):
    history_file = tmp_path / "vless-delay-history.json"
    monkeypatch.setattr(vless_control, "DELAY_HISTORY_FILE", history_file)
    profile_file = tmp_path / "profiles.json"
    controller = VlessControl(
        profile_file=profile_file, config_file=tmp_path / "config.json"
    )
    controller._save_store(
        {
            "version": 1,
            "profiles": [profile()],
            "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
            "selection": {"mode": "auto", "profile_id": None},
        },
        backup=False,
    )
    monkeypatch.setattr(controller, "_running", lambda: True)
    clock = {"now": datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(vless_control, "_utc_now", lambda: clock["now"])
    outcomes = iter([None, None, 143])

    def fake_exec(args, timeout=12, check=False, input_text=None):
        value = next(outcomes)
        return SimpleNamespace(
            returncode=0 if value is not None else 1,
            stdout=json.dumps({"delay": value}) if value is not None else "",
            stderr="",
        )

    monkeypatch.setattr(controller, "_exec", fake_exec)

    first = controller.test_delays()["results"][0]
    assert first["reachable"] is False
    assert first["consecutive_failures"] == 1
    assert first["unavailable_seconds"] == 0
    started_at = first["first_failed_at"]

    clock["now"] += timedelta(seconds=125)
    second = controller.test_delays()["results"][0]
    assert second["first_failed_at"] == started_at
    assert second["unavailable_seconds"] == 125
    assert second["consecutive_failures"] == 2

    # A new controller instance proves that history is read from persistent storage.
    restarted = VlessControl(
        profile_file=profile_file, config_file=tmp_path / "config.json"
    )
    persisted = restarted.get_delay_history()["results"][0]
    assert persisted["first_failed_at"] == started_at
    assert persisted["unavailable_seconds"] == 125

    clock["now"] += timedelta(seconds=180)
    recovered = controller.test_delays()["results"][0]
    assert recovered["reachable"] is True
    assert recovered["delay_ms"] == 143
    assert recovered["first_failed_at"] is None
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_outage_started_at"] == started_at
    assert recovered["last_outage_duration_seconds"] == 305
    assert recovered["last_recovered_at"] == "2026-10-20T10:05:05Z"
    assert history_file.exists()
    assert stat.S_IMODE(history_file.stat().st_mode) == 0o600


def _selection_observation(profile_id, *, epoch, delay_ms, mode="auto"):
    tag = f"vless-profile-{profile_id}"
    observed_at = datetime.fromtimestamp(epoch, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "observed_at": observed_at,
        "observed_at_epoch": epoch,
        "selection_mode": mode,
        "selected_outbound": "vless-auto" if mode == "auto" else tag,
        "active_outbound": tag,
        "active_delay_ms": delay_ms,
        "active_delay_observed_at": observed_at if delay_ms is not None else None,
        "profile_delays": {
            tag: {
                "delay_ms": delay_ms,
                "observed_at": observed_at if delay_ms is not None else None,
            }
        },
        "urltest_interval": "3m",
        "urltest_tolerance_ms": 50,
    }


def test_selection_history_records_observed_switch_and_survives_restart(tmp_path):
    history_file = tmp_path / "vless-selection-history.json"
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=history_file,
    )
    epoch = 1792490400.0
    assert (
        controller.record_selection_observation(
            _selection_observation(1, epoch=epoch, delay_ms=180)
        )
        is None
    )
    assert (
        controller.record_selection_observation(
            _selection_observation(1, epoch=epoch + 15, delay_ms=182)
        )
        is None
    )

    event = controller.record_selection_observation(
        _selection_observation(6, epoch=epoch + 30, delay_ms=277)
    )
    assert event is not None
    assert event["previous_outbound"] == "vless-profile-1"
    assert event["active_outbound"] == "vless-profile-6"
    assert event["previous_delay_ms"] == 182
    assert event["active_delay_ms"] == 277
    assert event["previous_delay_observed_at"] == "2026-10-20T10:00:15Z"
    assert event["active_delay_observed_at"] == "2026-10-20T10:00:30Z"
    assert event["reason"] == "not_determined"

    import stat

    assert stat.S_IMODE(history_file.stat().st_mode) == 0o600

    restarted = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=history_file,
    )
    history = restarted.get_selection_history()
    assert len(history["events"]) == 1
    assert history["events"][0]["event_id"] == event["event_id"]
    assert history["current"]["active_outbound"] == "vless-profile-6"


def test_selection_history_classifies_fresh_delay_based_switch(tmp_path):
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=tmp_path / "history.json",
    )
    epoch = 1792490400.0
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch, delay_ms=180)
    )
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch + 15, delay_ms=180)
    )

    event = controller.record_selection_observation(
        _selection_observation(6, epoch=epoch + 30, delay_ms=110)
    )

    assert event["measurement_freshness"] == "fresh"
    assert event["previous_delay_age_seconds"] == 15
    assert event["active_delay_age_seconds"] == 0
    assert event["previous_delay_fresh"] is True
    assert event["active_delay_fresh"] is True
    assert event["delay_improvement_ms"] == 70
    assert event["diagnostic_status"] == "consistent_with_latest_delays"
    assert "не доказывает" in event["diagnostic_details"]


def test_selection_history_flags_stale_previous_measurement(tmp_path):
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=tmp_path / "history.json",
    )
    epoch = 1792490400.0
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch, delay_ms=220)
    )
    previous = _selection_observation(1, epoch=epoch + 15, delay_ms=220)
    previous["profile_delays"]["vless-profile-1"]["observed_at"] = (
        datetime.fromtimestamp(epoch - 200, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    previous["active_delay_observed_at"] = previous["profile_delays"][
        "vless-profile-1"
    ]["observed_at"]
    controller.record_selection_observation(previous)

    event = controller.record_selection_observation(
        _selection_observation(6, epoch=epoch + 30, delay_ms=150)
    )

    assert event["measurement_freshness"] == "stale"
    assert event["previous_delay_age_seconds"] == 230
    assert event["active_delay_age_seconds"] == 0
    assert event["diagnostic_status"] == "stale_measurements"
    assert "старше интервала URLTest" in event["diagnostic_details"]


def test_selection_history_does_not_explain_fresh_but_slower_switch(tmp_path):
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=tmp_path / "history.json",
    )
    epoch = 1792490400.0
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch, delay_ms=180)
    )
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch + 15, delay_ms=180)
    )

    event = controller.record_selection_observation(
        _selection_observation(6, epoch=epoch + 30, delay_ms=220)
    )

    assert event["measurement_freshness"] == "fresh"
    assert event["delay_improvement_ms"] == -40
    assert event["diagnostic_status"] == "not_explained_by_latest_delays"
    assert "не доказывает ошибку sing-box" in event["diagnostic_details"]


def test_selection_history_marks_missing_delay_data_as_insufficient(tmp_path):
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=tmp_path / "history.json",
    )
    epoch = 1792490400.0
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch, delay_ms=180)
    )
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch + 15, delay_ms=180)
    )

    event = controller.record_selection_observation(
        _selection_observation(6, epoch=epoch + 30, delay_ms=None)
    )

    assert event["measurement_freshness"] == "incomplete"
    assert event["diagnostic_status"] == "insufficient_data"


def test_selection_timestamp_epoch_accepts_sing_box_nanosecond_timestamp():
    from vless_control import _selection_timestamp_epoch

    parsed = _selection_timestamp_epoch("2026-10-20T18:57:31.842531674Z")
    expected = datetime(
        2026, 10, 20, 18, 57, 31, 842531, tzinfo=timezone.utc
    ).timestamp()

    assert parsed is not None
    assert parsed == expected


def test_selection_history_retrospectively_classifies_legacy_events_without_persisting(
    tmp_path,
):
    import json

    history_file = tmp_path / "vless-selection-history.json"
    legacy_event = {
        "event_id": "legacy-1",
        "observed_at": "2026-10-20T19:03:44Z",
        "previous_selection_mode": "auto",
        "selection_mode": "auto",
        "previous_outbound": "vless-profile-1",
        "active_outbound": "vless-profile-6",
        "previous_delay_ms": 197,
        "active_delay_ms": 223,
        "previous_delay_observed_at": "2026-10-20T18:57:31.842531674Z",
        "active_delay_observed_at": "2026-10-20T19:03:31.877858682Z",
        "urltest_interval": "3m",
        "urltest_tolerance_ms": 50,
        "reason": "not_determined",
        "reason_details": "Legacy event without saved diagnostics.",
    }
    history_file.write_text(
        json.dumps({"version": 1, "last_observation": None, "events": [legacy_event]}),
        encoding="utf-8",
    )
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=history_file,
    )

    event = controller.get_selection_history()["events"][0]

    assert event["diagnostic_origin"] == "retrospective"
    assert event["measurement_freshness"] == "stale"
    assert event["previous_delay_age_seconds"] == 372
    assert event["active_delay_age_seconds"] == 12
    assert event["previous_delay_fresh"] is False
    assert event["active_delay_fresh"] is True
    assert event["diagnostic_status"] == "stale_measurements"
    # Read-time enrichment is deliberately non-persistent.
    stored = json.loads(history_file.read_text(encoding="utf-8"))
    assert "diagnostic_status" not in stored["events"][0]


def _availability_snapshot(epoch, samples, active_id=1):
    active_sample = samples.get(f"vless-profile-{active_id}", {})
    delay = active_sample.get("delay_ms") if isinstance(active_sample, dict) else None
    snapshot = _selection_observation(active_id, epoch=epoch, delay_ms=delay)
    snapshot["profile_delays"] = samples
    snapshot["active_delay_ms"] = delay
    snapshot["active_delay_observed_at"] = (
        active_sample.get("observed_at") if isinstance(active_sample, dict) else None
    )
    return snapshot


def test_urltest_availability_tracks_missing_result_and_recovery_persistently(tmp_path):
    history_file = tmp_path / "vless-selection-history.json"
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=history_file,
    )
    epoch = 1792490400.0

    def stamp(offset):
        return datetime.fromtimestamp(epoch + offset, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    baseline = _availability_snapshot(
        epoch,
        {
            "vless-profile-1": {"delay_ms": 180, "observed_at": stamp(0)},
            "vless-profile-2": {"delay_ms": 210, "observed_at": stamp(0)},
            "vless-profile-3": {"delay_ms": None, "observed_at": None},
        },
    )
    controller.record_selection_observation(baseline)
    initial = controller.get_selection_history()["profile_availability"]
    assert initial["1"]["status"] == "reachable"
    assert initial["3"]["status"] == "unknown"
    assert initial["3"]["first_missing_at"] is None

    missing = _availability_snapshot(
        epoch + 180,
        {
            "vless-profile-1": {"delay_ms": None, "observed_at": None},
            "vless-profile-2": {"delay_ms": 175, "observed_at": stamp(180)},
            "vless-profile-3": {"delay_ms": None, "observed_at": None},
        },
    )
    controller.record_selection_observation(missing)
    unavailable = controller.get_selection_history()["profile_availability"]
    assert unavailable["1"]["status"] == "no_result"
    assert unavailable["1"]["first_missing_at"] == stamp(180)
    assert unavailable["1"]["last_success_delay_ms"] == 180
    assert unavailable["3"]["status"] == "unknown"

    # Repeated empty snapshots must not move the first-missing timestamp.
    repeated = _availability_snapshot(
        epoch + 195,
        {
            "vless-profile-1": {"delay_ms": None, "observed_at": None},
            "vless-profile-2": {"delay_ms": 175, "observed_at": stamp(180)},
            "vless-profile-3": {"delay_ms": None, "observed_at": None},
        },
    )
    controller.record_selection_observation(repeated)
    still_unavailable = controller.get_selection_history()["profile_availability"]["1"]
    assert still_unavailable["first_missing_at"] == stamp(180)

    recovered = _availability_snapshot(
        epoch + 360,
        {
            "vless-profile-1": {"delay_ms": 190, "observed_at": stamp(360)},
            "vless-profile-2": {"delay_ms": 172, "observed_at": stamp(360)},
            "vless-profile-3": {"delay_ms": None, "observed_at": None},
        },
    )
    controller.record_selection_observation(recovered)
    restored = controller.get_selection_history()["profile_availability"]["1"]
    assert restored["status"] == "reachable"
    assert restored["first_missing_at"] is None
    assert restored["last_recovered_at"] == stamp(360)
    assert restored["last_outage_duration_seconds"] == 180

    restarted = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=history_file,
    )
    persisted = restarted.get_selection_history()["profile_availability"]["1"]
    assert persisted["status"] == "reachable"
    assert persisted["last_outage_duration_seconds"] == 180


def test_urltest_availability_seeds_legacy_snapshot_before_detecting_missing_result(
    tmp_path,
):
    import json

    history_file = tmp_path / "vless-selection-history.json"
    epoch = 1792490400.0

    def stamp(offset):
        return datetime.fromtimestamp(epoch + offset, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    baseline = _availability_snapshot(
        epoch,
        {
            "vless-profile-1": {"delay_ms": 180, "observed_at": stamp(0)},
            "vless-profile-2": {"delay_ms": 210, "observed_at": stamp(0)},
        },
    )
    history_file.write_text(
        json.dumps(
            {
                "version": 1,
                "last_observation": baseline,
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=history_file,
    )

    current = _availability_snapshot(
        epoch + 15,
        {
            "vless-profile-1": {"delay_ms": None, "observed_at": None},
            "vless-profile-2": {"delay_ms": 205, "observed_at": stamp(15)},
        },
    )
    controller.record_selection_observation(current)
    availability = controller.get_selection_history()["profile_availability"]
    assert availability["1"]["status"] == "no_result"
    assert availability["1"]["first_missing_at"] == stamp(15)
    assert availability["1"]["last_success_delay_ms"] == 180


def test_urltest_availability_does_not_call_first_empty_history_an_outage(tmp_path):
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=tmp_path / "vless-selection-history.json",
    )
    epoch = 1792490400.0
    snapshot = _availability_snapshot(
        epoch,
        {
            "vless-profile-1": {"delay_ms": None, "observed_at": None},
            "vless-profile-2": {"delay_ms": None, "observed_at": None},
        },
    )
    controller.record_selection_observation(snapshot)
    availability = controller.get_selection_history()["profile_availability"]
    assert availability["1"]["status"] == "unknown"
    assert availability["2"]["status"] == "unknown"
    assert availability["1"]["first_missing_at"] is None


def test_urltest_availability_marks_global_history_reset_as_ambiguous(tmp_path):
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=tmp_path / "vless-selection-history.json",
    )
    epoch = 1792490400.0

    def stamp(offset):
        return datetime.fromtimestamp(epoch + offset, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )

    controller.record_selection_observation(
        _availability_snapshot(
            epoch,
            {
                "vless-profile-1": {"delay_ms": 180, "observed_at": stamp(0)},
                "vless-profile-2": {"delay_ms": 210, "observed_at": stamp(0)},
            },
        )
    )
    controller.record_selection_observation(
        _availability_snapshot(
            epoch + 15,
            {
                "vless-profile-1": {"delay_ms": None, "observed_at": None},
                "vless-profile-2": {"delay_ms": None, "observed_at": None},
            },
        )
    )
    availability = controller.get_selection_history()["profile_availability"]
    assert availability["1"]["status"] == "unknown"
    assert availability["2"]["status"] == "unknown"
    assert availability["1"]["reason"] == "history_reset"
    assert availability["1"]["first_missing_at"] is None


def test_selection_history_is_bounded_to_200_events(tmp_path):
    history_file = tmp_path / "vless-selection-history.json"
    controller = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "config.json",
        selection_history_file=history_file,
    )
    epoch = 1792490400.0
    controller.record_selection_observation(
        _selection_observation(1, epoch=epoch, delay_ms=180)
    )
    for index in range(1, 206):
        profile_id = 2 if index % 2 else 1
        controller.record_selection_observation(
            _selection_observation(
                profile_id,
                epoch=epoch + index * 15,
                delay_ms=275 if profile_id == 2 else 180,
            )
        )
    history = controller.get_selection_history()
    assert len(history["events"]) == 200
    assert history["events"][-1]["active_outbound"] == "vless-profile-2"


def _selection_staging_controller(
    tmp_path, monkeypatch, selection, live_selected, live_active
):
    store = {
        "version": 1,
        "profiles": [
            profile(1, "at.example.com", "Austria"),
            profile(2, "lt.example.com", "Lithuania", uuid=TEST_UUID_2),
        ],
        "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
        "selection": selection,
    }
    profile_file = tmp_path / "vless-profiles.json"
    config_file = tmp_path / "sing-box-vless.json"
    profile_file.write_text(json.dumps(store), encoding="utf-8")
    config_file.write_text(json.dumps(_render_config(store)), encoding="utf-8")
    sing_box = tmp_path / "sing-box"
    service = tmp_path / "maxvpn-sing-box"
    sing_box.touch()
    service.touch()
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(vless_control, "SING_BOX", sing_box)
    monkeypatch.setattr(vless_control, "SERVICE", service)
    monkeypatch.setattr(vless_control, "BACKUP_DIR", backup_dir)

    commands = []

    def runner(args, timeout=12, check=False, input_text=None):
        args = [str(part) for part in args]
        commands.append(args)
        url = args[-1] if args else ""
        if url.endswith("/proxies/vless-out"):
            body = {"now": live_selected}
            return SimpleNamespace(returncode=0, stdout=json.dumps(body), stderr="")
        if url.endswith("/proxies/vless-auto"):
            body = {"now": live_active}
            return SimpleNamespace(returncode=0, stdout=json.dumps(body), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    controller = VlessControl(
        profile_file=profile_file,
        config_file=config_file,
        command_runner=runner,
    )
    monkeypatch.setattr(controller, "_running", lambda: True)
    monkeypatch.setattr(controller, "_read_mode", lambda: "wan")
    return controller, profile_file, commands


def test_select_outbound_stages_manual_choice_without_changing_live_runtime(
    tmp_path, monkeypatch
):
    controller, profile_file, commands = _selection_staging_controller(
        tmp_path,
        monkeypatch,
        {"mode": "auto", "profile_id": None},
        "vless-auto",
        "vless-profile-1",
    )

    result = controller.select_outbound(2)

    saved = json.loads(profile_file.read_text(encoding="utf-8"))
    assert saved["selection"] == {"mode": "manual", "profile_id": 2}
    assert result["action"] == "selection-staged"
    assert result["selected_outbound"] == "vless-auto"
    assert result["active_outbound"] == "vless-profile-1"
    assert result["selection_mode"] == "auto"
    assert result["desired_selection_mode"] == "manual"
    assert result["desired_profile_id"] == 2
    assert result["selection_pending"] is True
    assert result["config_dirty"] is True
    assert not any(
        "-X" in command or "--data-binary" in command for command in commands
    )


def test_select_outbound_stages_auto_choice_without_changing_live_manual_runtime(
    tmp_path, monkeypatch
):
    controller, profile_file, commands = _selection_staging_controller(
        tmp_path,
        monkeypatch,
        {"mode": "manual", "profile_id": 2},
        "vless-profile-2",
        "vless-profile-1",
    )

    result = controller.select_outbound(None)

    saved = json.loads(profile_file.read_text(encoding="utf-8"))
    assert saved["selection"] == {"mode": "auto", "profile_id": None}
    assert result["action"] == "selection-staged"
    assert result["selected_outbound"] == "vless-profile-2"
    assert result["active_outbound"] == "vless-profile-2"
    assert result["selection_mode"] == "manual"
    assert result["desired_selection_mode"] == "auto"
    assert result["desired_profile_id"] is None
    assert result["selection_pending"] is True
    assert result["config_dirty"] is True
    assert not any(
        "-X" in command or "--data-binary" in command for command in commands
    )


def test_selection_pending_clears_only_when_live_selector_matches_saved_choice(
    tmp_path, monkeypatch
):
    controller, _profile_file, _commands = _selection_staging_controller(
        tmp_path,
        monkeypatch,
        {"mode": "manual", "profile_id": 2},
        "vless-profile-2",
        "vless-profile-1",
    )

    result = controller.get_state()

    assert result["desired_selection_mode"] == "manual"
    assert result["desired_profile_id"] == 2
    assert result["selection_mode"] == "manual"
    assert result["selected_outbound"] == "vless-profile-2"
    assert result["active_outbound"] == "vless-profile-2"
    assert result["selection_pending"] is False


def _wan_fallback_controller(
    tmp_path, *, mode="vless", selection=None, running=True, enabled=True
):
    profiles = [
        profile(),
        profile(2, "second.example.com", "Second", uuid=TEST_UUID_2),
    ]
    selection = selection or {"mode": "auto", "profile_id": None}
    controller = VlessControl(
        profile_file=tmp_path / "vless-profiles.json",
        config_file=tmp_path / "sing-box.json",
    )
    controller._save_store(
        {
            "version": 1,
            "profiles": profiles,
            "settings": {
                "urltest_interval": "3m",
                "urltest_tolerance_ms": 50,
                "wan_fallback_enabled": enabled,
            },
            "selection": selection,
        },
        backup=False,
    )
    runtime = {"mode": mode, "running": running}
    mode_calls = []

    def set_mode(next_mode, *, automatic_fallback=False):
        mode_calls.append((next_mode, automatic_fallback))
        runtime["mode"] = next_mode
        return {}

    controller._read_mode = lambda: runtime["mode"]
    controller._running = lambda: runtime["running"]
    controller._runtime_info = lambda _store: {
        "selection_mode": selection["mode"],
        "active_outbound": (
            "vless-profile-" + str(selection["profile_id"])
            if selection["mode"] == "manual"
            else "vless-profile-1"
        ),
    }
    controller.set_mode = set_mode
    return controller, runtime, mode_calls, profiles


def _probe_results(profiles, reachable_ids=()):
    reachable_ids = set(reachable_ids)
    return [
        {
            "profile_id": int(item["id"]),
            "delay_ms": 40 if int(item["id"]) in reachable_ids else None,
            "reachable": int(item["id"]) in reachable_ids,
        }
        for item in profiles
    ]


def test_wan_fallback_is_opt_in_and_disabled_by_default(tmp_path):
    controller, _runtime, mode_calls, _profiles = _wan_fallback_controller(
        tmp_path, enabled=False
    )
    controller._probe_profiles = lambda _profiles: pytest.fail(
        "disabled WAN fallback must not probe profiles"
    )

    result = controller.monitor_wan_fallback()

    assert result == {"action": "disabled", "active": False}
    assert mode_calls == []
    assert controller._load_store()["settings"]["wan_fallback_enabled"] is False


def test_auto_wan_fallback_waits_for_two_all_profile_failures(tmp_path):
    controller, runtime, mode_calls, profiles = _wan_fallback_controller(tmp_path)
    controller._probe_profiles = lambda candidates: _probe_results(candidates)
    saved_selection = controller._load_store()["selection"]

    first = controller.monitor_wan_fallback()
    second = controller.monitor_wan_fallback()

    assert first["action"] == "checked"
    assert second == {"action": "fallback-to-wan", "active": True}
    assert runtime["mode"] == "wan"
    assert mode_calls == [("wan", True)]
    assert controller._load_store()["selection"] == saved_selection
    assert len(profiles) == 2


def test_auto_keeps_vless_when_any_enabled_profile_is_reachable(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(tmp_path)
    controller._probe_profiles = lambda candidates: _probe_results(candidates, {2})

    for _ in range(3):
        result = controller.monitor_wan_fallback()

    assert result["action"] == "checked"
    assert runtime["mode"] == "vless"
    assert mode_calls == []


def test_manual_wan_fallback_probes_and_preserves_only_pinned_profile(tmp_path):
    selection = {"mode": "manual", "profile_id": 2}
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(
        tmp_path, selection=selection
    )
    probed_ids = []

    def probe(candidates):
        probed_ids.extend(int(item["id"]) for item in candidates)
        return _probe_results(candidates)

    controller._probe_profiles = probe
    controller.monitor_wan_fallback()
    result = controller.monitor_wan_fallback()

    assert result == {"action": "fallback-to-wan", "active": True}
    assert probed_ids == [2, 2]
    assert controller._load_store()["selection"] == selection
    assert runtime["mode"] == "wan"
    assert mode_calls == [("wan", True)]


def test_wan_fallback_recovers_after_two_successful_profile_checks(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(tmp_path)
    check_results = iter(
        [
            {1: False, 2: False},
            {1: False, 2: False},
            {1: True, 2: False},
            {1: True, 2: False},
        ]
    )
    controller._probe_profiles = lambda candidates: _probe_results(
        candidates,
        [
            profile_id
            for profile_id, reachable in next(check_results).items()
            if reachable
        ],
    )

    controller.monitor_wan_fallback()
    controller.monitor_wan_fallback()
    first_recovery_check = controller.monitor_wan_fallback()
    recovered = controller.monitor_wan_fallback()

    assert first_recovery_check["action"] == "checked"
    assert recovered == {"action": "recovered-to-vless", "active": False}
    assert runtime["mode"] == "vless"
    assert mode_calls == [("wan", True), ("vless", True)]
    assert controller._load_store()["selection"] == {
        "mode": "auto",
        "profile_id": None,
    }


def test_runtime_failure_uses_wan_only_after_two_checks_when_enabled(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(
        tmp_path, running=False
    )

    first = controller.monitor_wan_fallback()
    second = controller.monitor_wan_fallback()

    assert first["action"] == "runtime-unhealthy"
    assert second == {"action": "fallback-to-wan", "active": True}
    assert runtime["mode"] == "wan"
    assert mode_calls == [("wan", True)]


def test_failed_restore_keeps_wan_fallback_setting_enabled(tmp_path):
    controller, _runtime, _mode_calls, _profiles = _wan_fallback_controller(
        tmp_path, mode="wan"
    )
    controller._save_wan_fallback_state(
        {
            "active": True,
            "selection_mode": "auto",
            "fallback_started_at": "2026-11-06T00:00:00Z",
            "profile_counters": {},
        }
    )

    def fail_restore(*_args, **_kwargs):
        raise VlessControlError("restore failed")

    controller.set_mode = fail_restore
    with pytest.raises(
        VlessControlError, match="политика WAN fallback оставлена включённой"
    ):
        controller.update_settings(
            {
                "urltest_interval": "3m",
                "urltest_tolerance_ms": 50,
                "wan_fallback_enabled": False,
            }
        )

    assert controller._load_store()["settings"]["wan_fallback_enabled"] is True
    assert controller._load_wan_fallback_state()["active"] is True


def test_recovery_starts_sing_box_while_lan_stays_on_wan(tmp_path):
    controller, runtime, mode_calls, profiles = _wan_fallback_controller(
        tmp_path, mode="wan", running=False
    )
    controller._save_wan_fallback_state(
        {
            "active": True,
            "selection_mode": "auto",
            "fallback_started_at": "2026-11-06T00:00:00Z",
            "profile_counters": {},
        }
    )
    starts = []

    def start():
        starts.append(True)
        runtime["running"] = True

    controller.start = start
    controller._probe_profiles = lambda candidates: _probe_results(candidates, {1})

    first = controller.monitor_wan_fallback()
    second = controller.monitor_wan_fallback()

    assert first["action"] == "checked"
    assert second["action"] == "recovered-to-vless"
    assert starts == [True]
    assert runtime["mode"] == "vless"
    assert mode_calls == [("vless", True)]
    assert len(profiles) == 2


def test_explicit_stop_clears_wan_fallback_marker(tmp_path):
    from subprocess import CompletedProcess

    controller, _runtime, _mode_calls, _profiles = _wan_fallback_controller(
        tmp_path, mode="wan", running=False
    )
    controller._save_wan_fallback_state(
        {
            "active": True,
            "selection_mode": "manual",
            "fallback_started_at": "2026-11-06T00:00:00Z",
            "profile_counters": {},
        }
    )
    commands = []

    def exec_command(args, **_kwargs):
        commands.append(args)
        return CompletedProcess(args, 0, stdout="wan", stderr="")

    controller._exec = exec_command
    controller._runtime_info = lambda _store: {}

    controller.stop()

    assert commands == [["/usr/bin/vpn-lan-vless-stop"]]
    state = controller._load_wan_fallback_state()
    assert state["active"] is False
    assert state["selection_mode"] is None


def test_failed_vless_switch_restores_existing_amneziawg_mode(tmp_path, monkeypatch):
    from subprocess import CompletedProcess

    binary = tmp_path / "sing-box"
    binary.write_text("test")
    mode_file = tmp_path / "runtime-mode"
    mode_file.write_text("vpn\n")
    profile_file = tmp_path / "profiles.json"
    profile_file.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [profile()],
                "settings": {"urltest_interval": "3m", "urltest_tolerance_ms": 50},
                "selection": {"mode": "auto", "profile_id": None},
            }
        )
    )
    monkeypatch.setattr(vless_control, "SING_BOX", binary)
    monkeypatch.setattr(vless_control, "MODE_FILE", mode_file)
    commands = []

    def runner(args, **_kwargs):
        command = [str(item) for item in args]
        commands.append(command)
        if command[:2] == [str(binary), "check"]:
            return CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["/usr/bin/vpn-lan-vless-on"]:
            return CompletedProcess(command, 1, stdout="", stderr="VLESS route failed")
        if command == ["/usr/bin/vpn-lan-on"]:
            mode_file.write_text("vpn\n")
        return CompletedProcess(command, 0, stdout="", stderr="")

    controller = VlessControl(
        profile_file=profile_file,
        config_file=tmp_path / "runtime.json",
        command_runner=runner,
    )
    controller._running = lambda: True
    controller._config_differs = lambda _store: False

    with pytest.raises(VlessControlError, match="Не удалось переключить режим"):
        controller.set_mode("vless")

    assert mode_file.read_text().strip() == "vpn"
    assert ["/usr/bin/vpn-lan-on"] in commands
    assert ["/usr/bin/vpn-lan-off"] not in commands


def test_runtime_failure_does_not_fallback_without_enabled_auto_profiles(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(
        tmp_path, running=False
    )
    store = controller._load_store()
    store["profiles"] = []
    controller._save_store(store, backup=False)
    controller._probe_profiles = lambda _profiles: pytest.fail(
        "There are no profiles to probe"
    )

    first = controller.monitor_wan_fallback()
    second = controller.monitor_wan_fallback()

    assert first == {"action": "no-profiles", "active": False}
    assert second == {"action": "no-profiles", "active": False}
    assert runtime["mode"] == "vless"
    assert mode_calls == []
    assert controller._load_wan_fallback_state()["active"] is False


def test_runtime_failure_does_not_fallback_for_disabled_manual_profile(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(
        tmp_path,
        selection={"mode": "manual", "profile_id": 2},
        running=False,
    )
    store = controller._load_store()
    for item in store["profiles"]:
        if int(item["id"]) == 2:
            item["enabled"] = False
    controller._save_store(store, backup=False)
    controller._probe_profiles = lambda _profiles: pytest.fail(
        "The disabled pinned profile must not be probed"
    )

    result = controller.monitor_wan_fallback()

    assert result == {"action": "no-profiles", "active": False}
    assert runtime["mode"] == "vless"
    assert mode_calls == []
    assert controller._load_wan_fallback_state()["active"] is False


def test_runtime_failure_counters_are_not_persisted_to_flash(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(
        tmp_path, running=False
    )

    first = controller.monitor_wan_fallback()

    assert first == {"action": "runtime-unhealthy", "active": False}
    assert not controller.wan_fallback_state_file.exists()

    second = controller.monitor_wan_fallback()

    assert second == {"action": "fallback-to-wan", "active": True}
    assert runtime["mode"] == "wan"
    assert mode_calls == [("wan", True)]

    persisted = json.loads(
        controller.wan_fallback_state_file.read_text(encoding="utf-8")
    )
    assert set(persisted) == {
        "active",
        "selection_mode",
        "fallback_started_at",
    }
    assert persisted["active"] is True


def test_profile_probe_counters_are_not_persisted_to_flash(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(tmp_path)
    controller._probe_profiles = lambda candidates: _probe_results(candidates)

    first = controller.monitor_wan_fallback()

    assert first["action"] == "checked"
    assert not controller.wan_fallback_state_file.exists()

    second = controller.monitor_wan_fallback()

    assert second == {"action": "fallback-to-wan", "active": True}
    assert runtime["mode"] == "wan"
    assert mode_calls == [("wan", True)]

    persisted = json.loads(
        controller.wan_fallback_state_file.read_text(encoding="utf-8")
    )
    assert set(persisted) == {
        "active",
        "selection_mode",
        "fallback_started_at",
    }


def test_active_manual_fallback_waits_for_pinned_profile_and_recovers(tmp_path):
    controller, runtime, mode_calls, _profiles = _wan_fallback_controller(
        tmp_path,
        mode="wan",
        selection={"mode": "manual", "profile_id": 2},
    )
    controller._save_wan_fallback_state(
        {
            "active": True,
            "selection_mode": "manual",
            "fallback_started_at": "2026-11-08T00:00:00Z",
        }
    )

    store = controller._load_store()
    for item in store["profiles"]:
        if int(item["id"]) == 2:
            item["enabled"] = False
    controller._save_store(store, backup=False)

    controller._probe_profiles = lambda _profiles: pytest.fail(
        "Disabled pinned profile must not be probed"
    )

    waiting = controller.monitor_wan_fallback()

    assert waiting == {"action": "no-profiles", "active": True}
    assert runtime["mode"] == "wan"
    assert mode_calls == []

    store = controller._load_store()
    for item in store["profiles"]:
        if int(item["id"]) == 2:
            item["enabled"] = True
    controller._save_store(store, backup=False)

    controller._probe_profiles = lambda candidates: _probe_results(candidates, {2})

    first = controller.monitor_wan_fallback()
    second = controller.monitor_wan_fallback()

    assert first["action"] == "checked"
    assert second == {"action": "recovered-to-vless", "active": False}
    assert runtime["mode"] == "vless"
    assert mode_calls == [("vless", True)]
