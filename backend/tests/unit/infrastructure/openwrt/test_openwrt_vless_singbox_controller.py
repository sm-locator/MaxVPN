from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from backend.infrastructure.openwrt.openwrt_vless_singbox_controller import (
    OpenWrtVlessSingBoxController,
)


def result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


class FakeExecutor:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def run(self, command, stdin=None):
        self.calls.append((command, stdin))
        if self.results:
            return self.results.pop(0)
        return result()


def sample_config():
    return {
        "inbounds": [
            {
                "type": "tun",
                "tag": "maxvpn-tun-in",
                "interface_name": "maxvpn0",
                "address": ["172.19.0.1/30"],
                "mtu": 1380,
                "auto_route": False,
            }
        ],
        "outbounds": [
            {
                "type": "vless",
                "tag": "vless-out",
                "server": "example.com",
                "server_port": 443,
                "uuid": "00000000-0000-0000-0000-000000000000",
                "packet_encoding": "xudp",
                "flow": "xtls-rprx-vision",
                "tls": {
                    "enabled": True,
                    "server_name": "example.com",
                    "reality": {
                        "enabled": True,
                        "public_key": "synthetic-public-key",
                        "short_id": "abcd",
                    },
                },
            },
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "auto_detect_interface": True,
            "final": "vless-out",
        },
    }


def test_install_verified_binary_checks_version_and_does_not_overwrite_unknown():
    executor = FakeExecutor()
    controller = OpenWrtVlessSingBoxController(executor)

    controller.install_verified_binary()

    command, _ = executor.calls[0]
    script = command[2]

    assert "/root/sing-box-test" in script
    assert "/usr/bin/sing-box" in script
    assert "sing-box version 1.14.3" in script
    assert "Refusing to overwrite" in script


def test_service_script_uses_procd_and_prechecks_configuration():
    executor = FakeExecutor()
    controller = OpenWrtVlessSingBoxController(executor)

    controller.install_service_script()

    command, stdin = executor.calls[0]
    assert command[:2] == ["sh", "-c"]
    assert stdin is not None
    assert "USE_PROCD=1" in stdin
    assert '"$BIN" check -c "$CONFIG"' in stdin
    assert 'procd_set_param command "$BIN" run -c "$CONFIG"' in stdin
    assert "vpn-lan-on" not in stdin
    assert "WireGuard" not in stdin


def test_install_config_sends_json_via_stdin_and_uses_atomic_install():
    executor = FakeExecutor()
    controller = OpenWrtVlessSingBoxController(executor)
    config = sample_config()

    controller.install_config(config)

    command, stdin = executor.calls[0]
    assert command[:2] == ["sh", "-c"]
    payload = json.loads(stdin)
    assert payload == config
    assert "mktemp" in command[2]
    assert '"$bin" check -c "$tmp"' in command[2]
    assert "chmod 600" in command[2]
    assert "mv -f" in command[2]


def test_backup_config_keeps_credentials_on_router_and_returns_generated_path():
    backup = OpenWrtVlessSingBoxController.CONFIG_PATH + ".maxvpn-backup-" + "a" * 32
    executor = FakeExecutor([result(stdout=backup + "\n")])
    controller = OpenWrtVlessSingBoxController(executor)

    assert controller.backup_config() == backup
    command, stdin = executor.calls[0]
    assert command[:2] == ["sh", "-c"]
    assert "cp -p" in command[2]
    assert "chmod 600" in command[2]
    assert stdin is None
    assert "uuid" not in (stdin or "")


def test_backup_config_rejects_unexpected_remote_path():
    executor = FakeExecutor([result(stdout="/tmp/not-a-maxvpn-backup\n")])
    controller = OpenWrtVlessSingBoxController(executor)

    with pytest.raises(ValueError, match="Invalid sing-box config backup path"):
        controller.backup_config()


def test_restore_config_validates_backup_and_checks_before_atomic_replace():
    backup = OpenWrtVlessSingBoxController.CONFIG_PATH + ".maxvpn-backup-" + "b" * 32
    executor = FakeExecutor()
    controller = OpenWrtVlessSingBoxController(executor)

    controller.restore_config(backup)

    script = executor.calls[0][0][2]
    assert "VLESS config backup is missing" in script
    assert '"$bin" check -c "$tmp"' in script
    assert 'mv -f "$tmp" "$dst"' in script
    assert 'rm -f "$bak"' in script


def test_restore_config_rejects_arbitrary_path():
    controller = OpenWrtVlessSingBoxController(FakeExecutor())

    with pytest.raises(ValueError, match="Invalid sing-box config backup path"):
        controller.restore_config("/tmp/other-file")


def test_restore_config_removes_failed_config_when_no_previous_config_existed():
    executor = FakeExecutor()
    controller = OpenWrtVlessSingBoxController(executor)

    controller.restore_config(None)

    assert "rm -f" in executor.calls[0][0][2]
    assert OpenWrtVlessSingBoxController.CONFIG_PATH in executor.calls[0][0][2]


def test_config_rejects_auto_route_to_preserve_maxvpn_routing():
    executor = FakeExecutor()
    controller = OpenWrtVlessSingBoxController(executor)
    config = sample_config()
    config["inbounds"][0]["auto_route"] = True

    with pytest.raises(ValueError, match="auto_route must be false"):
        controller.install_config(config)

    assert executor.calls == []


def test_config_rejects_wrong_tun_interface():
    controller = OpenWrtVlessSingBoxController(FakeExecutor())
    config = sample_config()
    config["inbounds"][0]["interface_name"] = "tun0"

    with pytest.raises(ValueError, match="TUN interface"):
        controller.install_config(config)


def test_config_rejects_missing_vless_outbound():
    controller = OpenWrtVlessSingBoxController(FakeExecutor())
    config = sample_config()
    config["outbounds"] = [{"type": "direct", "tag": "direct"}]

    with pytest.raises(ValueError, match="vless-out"):
        controller.install_config(config)


def test_status_reports_service_running():
    payload = json.dumps(
        {
            "maxvpn-sing-box": {
                "instances": {
                    "instance1": {
                        "running": True,
                        "pid": 1234,
                    }
                }
            }
        }
    )
    executor = FakeExecutor([result(stdout=payload)])
    controller = OpenWrtVlessSingBoxController(executor)

    assert controller.status() == {"installed": True, "running": True}


def test_status_reports_service_not_running():
    payload = json.dumps(
        {
            "maxvpn-sing-box": {
                "instances": {
                    "instance1": {
                        "running": False,
                    }
                }
            }
        }
    )
    executor = FakeExecutor([result(stdout=payload)])
    controller = OpenWrtVlessSingBoxController(executor)

    assert controller.status() == {"installed": True, "running": False}


def test_status_detects_installed_files_when_ubus_has_no_service():
    executor = FakeExecutor(
        [
            result(stdout="{}"),  # procd omits the stopped service
            result(),  # binary, init script and config files exist
        ]
    )
    controller = OpenWrtVlessSingBoxController(executor)

    assert controller.status() == {"installed": True, "running": False}
    assert executor.calls[1][0] == [
        "sh",
        "-c",
        "test -x /usr/bin/sing-box && "
        "test -x /etc/init.d/maxvpn-sing-box && "
        "test -f /etc/maxvpn/sing-box-vless.json",
    ]


def test_status_reports_not_installed_when_ubus_and_files_are_absent():
    executor = FakeExecutor(
        [
            result(stdout="{}"),
            result(returncode=1),  # one or more installation files are absent
        ]
    )
    controller = OpenWrtVlessSingBoxController(executor)

    assert controller.status() == {"installed": False, "running": False}


def test_nonzero_remote_exit_is_reported():
    executor = FakeExecutor([result(stderr="binary version mismatch", returncode=73)])
    controller = OpenWrtVlessSingBoxController(executor)

    with pytest.raises(RuntimeError, match="binary version mismatch"):
        controller.install_verified_binary()


def test_start_enables_autostart_only_after_running_status_is_confirmed():
    payload = json.dumps(
        {"maxvpn-sing-box": {"instances": {"instance1": {"running": True}}}}
    )
    executor = FakeExecutor(
        [
            result(),  # start
            result(stdout=payload),  # status
            result(),  # enable
        ]
    )
    controller = OpenWrtVlessSingBoxController(executor)

    controller.start()

    assert executor.calls[0][0] == [
        "/etc/init.d/maxvpn-sing-box",
        "start",
    ]
    assert executor.calls[1][0][:4] == [
        "ubus",
        "call",
        "service",
        "list",
    ]
    assert executor.calls[2][0] == [
        "/etc/init.d/maxvpn-sing-box",
        "enable",
    ]


def test_selection_history_reads_appliance_journal_without_probing():
    import json
    from types import SimpleNamespace

    from backend.infrastructure.openwrt.openwrt_vless_singbox_controller import (
        OpenWrtVlessSingBoxController,
    )

    payload = {
        "monitor": {"enabled": True, "interval_seconds": 15, "last_error": None},
        "current": {"selection_mode": "auto", "active_outbound": "vless-profile-1"},
        "events": [],
    }

    class Executor:
        def __init__(self):
            self.commands = []

        def run(self, command):
            self.commands.append(command)
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    executor = Executor()
    controller = OpenWrtVlessSingBoxController(executor)
    assert controller.selection_history() == payload
    assert len(executor.commands) == 1
    assert (
        "127.0.0.1:8787/api/appliance/v1/vless/selection-history"
        in executor.commands[0][-1]
    )


def test_outbound_delays_uses_cloudflare_generate_204():
    executor = FakeExecutor([result(stdout=json.dumps({"delay": 123}))])
    controller = OpenWrtVlessSingBoxController(executor)

    assert controller.test_outbound_delays(["vless-profile-1"]) == {
        "vless-profile-1": 123
    }

    assert len(executor.calls) == 1
    command, stdin = executor.calls[0]
    assert stdin is None
    assert command[:2] == ["sh", "-c"]

    script = command[2]
    assert "--data-urlencode 'url=https://cp.cloudflare.com/generate_204'" in script


def test_set_wan_fallback_enabled_posts_and_confirms_router_state():
    response = {
        "settings": {"wan_fallback_enabled": False},
        "wan_fallback_active": True,
    }
    executor = FakeExecutor([result(stdout=json.dumps(response))])
    controller = OpenWrtVlessSingBoxController(executor)

    actual = controller.set_wan_fallback_enabled(False)

    assert actual == {
        "kill_switch_enabled": True,
        "wan_fallback_active": True,
    }

    assert len(executor.calls) == 1
    command, stdin = executor.calls[0]
    assert command[:2] == ["sh", "-c"]
    assert stdin is None

    script = command[2]
    assert "curl -fsS --max-time 8 -X POST" in script
    assert "http://127.0.0.1:8787/api/appliance/v1/vless/settings" in script
    assert "-H 'Content-Type: application/json'" in script
    assert "--data-binary '{\"wan_fallback_enabled\":false}'" in script


@pytest.mark.parametrize(
    ("remote_result", "expected_error"),
    [
        (
            result(stdout="not-json"),
            "invalid Kill Switch state",
        ),
        (
            result(
                stdout=json.dumps(
                    {
                        "settings": {"wan_fallback_enabled": True},
                        "wan_fallback_active": False,
                    }
                )
            ),
            "did not confirm",
        ),
        (
            result(stderr="connection refused", returncode=7),
            "Unable to update the Kill Switch",
        ),
    ],
)
def test_set_wan_fallback_enabled_rejects_unconfirmed_router_state(
    remote_result, expected_error
):
    executor = FakeExecutor([remote_result])
    controller = OpenWrtVlessSingBoxController(executor)

    with pytest.raises(RuntimeError, match=expected_error):
        controller.set_wan_fallback_enabled(False)


def test_set_wan_fallback_enabled_rejects_non_boolean_input():
    executor = FakeExecutor()
    controller = OpenWrtVlessSingBoxController(executor)

    with pytest.raises(ValueError, match="must be a boolean"):
        controller.set_wan_fallback_enabled(1)

    assert executor.calls == []
