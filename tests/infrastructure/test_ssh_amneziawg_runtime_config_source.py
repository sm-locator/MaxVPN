from unittest.mock import Mock

import pytest

from backend.infrastructure.wireguard.ssh_amneziawg_runtime_config_source import (
    SSHAmneziaWGRuntimeConfigSource,
)
from backend.models.command_result import CommandResult

RUNTIME_CONFIG = """[Interface]
ListenPort = 47182
PrivateKey = interface-private
Jc = 5
Jmin = 2
Jmax = 9
S1 = 0
S2 = 0
S3 = 0
S4 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4

[Peer]
PublicKey = peer-public
PresharedKey = peer-preshared
AdvancedSecurity = on
AllowedIPs = 0.0.0.0/0
Endpoint = 109.172.55.99:51820
PersistentKeepalive = 25
"""


EXPECTED = """[Interface]
PrivateKey = interface-private
Jc = 5
Jmin = 2
Jmax = 9
S1 = 0
S2 = 0
S3 = 0
S4 = 0
H1 = 1
H2 = 2
H3 = 3
H4 = 4

[Peer]
PublicKey = peer-public
PresharedKey = peer-preshared
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
Endpoint = 109.172.55.99:51820
"""


def make_executor(
    result: CommandResult,
) -> Mock:
    executor = Mock()
    executor.run.return_value = result
    return executor


def test_read_normalizes_active_runtime() -> None:
    executor = make_executor(
        CommandResult(
            stdout=RUNTIME_CONFIG,
            stderr="",
            returncode=0,
        ),
    )

    source = SSHAmneziaWGRuntimeConfigSource(executor)

    assert source.read("WireGuard") == EXPECTED

    executor.run.assert_called_once_with(
        [
            "awg",
            "showconf",
            "WireGuard",
        ]
    )


def test_read_rejects_command_failure() -> None:
    executor = make_executor(
        CommandResult(
            stdout="",
            stderr="permission denied",
            returncode=1,
        ),
    )

    source = SSHAmneziaWGRuntimeConfigSource(executor)

    with pytest.raises(
        RuntimeError,
        match="awg_showconf_failed",
    ):
        source.read()


def test_read_rejects_empty_output() -> None:
    executor = make_executor(
        CommandResult(
            stdout="",
            stderr="",
            returncode=0,
        ),
    )

    source = SSHAmneziaWGRuntimeConfigSource(executor)

    with pytest.raises(
        RuntimeError,
        match="awg_showconf_empty",
    ):
        source.read()
