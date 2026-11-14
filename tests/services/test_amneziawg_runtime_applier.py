from unittest.mock import Mock

from backend.models.command_result import CommandResult
from backend.ports.remote_command_executor import RemoteCommandExecutor
from backend.services.amneziawg_config_parser import (
    AmneziaWGConfigParser,
)
from backend.services.amneziawg_runtime_applier import (
    AmneziaWGRuntimeApplier,
)

PROVIDER_CONFIG = """\
[Interface]
PrivateKey = private-key
Address = 10.9.9.200/32
DNS = 1.1.1.1
MTU = 1380
Jc = 5
Jmin = 49
Jmax = 998
S1 = 17
S2 = 110
S3 = 1
S4 = 2
H1 = 1597513488-1927637527
H2 = 1959162374-2134706886
H3 = 2135520142-2141053315
H4 = 2143034152-2146422435
I1 = <r 2><b 0x858000010001000000000669636c6f756403636f6d0000010001c00c000100010000105a00044d583737>
I2 = 0
I3 = 0
I4 = 0
I5 = 0

[Peer]
PublicKey = server-public-key
AllowedIPs = 0.0.0.0/0
Endpoint = 194.26.192.36:39743
PersistentKeepalive = 25
PresharedKey = psk
"""


def make_config():
    return AmneziaWGConfigParser().parse(PROVIDER_CONFIG)


def test_plan_contains_only_runtime_operations():
    plan = AmneziaWGRuntimeApplier().plan(make_config())

    assert plan.interface == "WireGuard"
    assert plan.runtime_path == "/tmp/maxvpn-awg-runtime.conf"

    assert plan.upload_command[0:2] == ("sh", "-c")
    assert plan.sync_command == (
        "awg",
        "syncconf",
        "WireGuard",
        "/tmp/maxvpn-awg-runtime.conf",
    )

    assert "S3 = 1" in plan.runtime_config
    assert "S4 = 2" in plan.runtime_config
    assert "I1 = <r 2><b 0x85800001" in plan.runtime_config

    assert "Address =" not in plan.runtime_config
    assert "DNS =" not in plan.runtime_config
    assert "MTU =" not in plan.runtime_config


def test_plan_contains_no_lifecycle_operations():
    plan = AmneziaWGRuntimeApplier().plan(make_config())

    command_text = " ".join(
        [
            *plan.upload_command,
            *plan.sync_command,
        ]
    )

    for forbidden in (
        "ifdown",
        "ifup",
        "network restart",
        "network reload",
        "firewall restart",
        "reboot",
    ):
        assert forbidden not in command_text


def test_apply_uploads_then_syncs():
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.side_effect = [
        CommandResult(stdout="", stderr="", returncode=0),
        CommandResult(stdout="", stderr="", returncode=0),
    ]

    service = AmneziaWGRuntimeApplier(
        command_executor=executor,
    )

    result = service.apply(make_config())

    assert result.uploaded is True
    assert result.applied is True
    assert result.upload_returncode == 0
    assert result.sync_returncode == 0
    assert result.reason is None

    assert executor.run.call_count == 2

    first_command = executor.run.call_args_list[0].args[0]
    second_command = executor.run.call_args_list[1].args[0]

    assert first_command[0:2] == ["sh", "-c"]
    assert second_command == [
        "awg",
        "syncconf",
        "WireGuard",
        "/tmp/maxvpn-awg-runtime.conf",
    ]


def test_apply_stops_when_upload_fails():
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = CommandResult(
        stdout="",
        stderr="upload failed",
        returncode=1,
    )

    service = AmneziaWGRuntimeApplier(
        command_executor=executor,
    )

    result = service.apply(make_config())

    assert result.uploaded is False
    assert result.applied is False
    assert result.upload_returncode == 1
    assert result.sync_returncode is None
    assert result.reason == "runtime_config_upload_failed: upload failed"

    executor.run.assert_called_once()


def test_apply_stops_when_syncconf_fails():
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.side_effect = [
        CommandResult(stdout="", stderr="", returncode=0),
        CommandResult(
            stdout="",
            stderr="syncconf failed",
            returncode=1,
        ),
    ]

    service = AmneziaWGRuntimeApplier(
        command_executor=executor,
    )

    result = service.apply(make_config())

    assert result.uploaded is True
    assert result.applied is False
    assert result.upload_returncode == 0
    assert result.sync_returncode == 1
    assert result.reason == "awg_syncconf_failed: syncconf failed"

    assert executor.run.call_count == 2


def test_apply_requires_executor():
    service = AmneziaWGRuntimeApplier()

    try:
        service.apply(make_config())
    except RuntimeError as exc:
        assert str(exc) == ("RemoteCommandExecutor is required for apply()")
    else:
        raise AssertionError("RuntimeError was not raised")
