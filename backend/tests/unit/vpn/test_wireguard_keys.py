from unittest.mock import Mock

from app.vpn.executors import CommandResult
from app.vpn.wireguard.keys import (
    WireGuardKeyGenerator,
    WireGuardKeyPair,
)


def test_generate_keypair() -> None:
    executor = Mock()

    executor.run.side_effect = [
        CommandResult(
            stdout="private_key",
            stderr="",
            returncode=0,
        ),
        CommandResult(
            stdout="public_key",
            stderr="",
            returncode=0,
        ),
    ]

    generator = WireGuardKeyGenerator(executor)

    result = generator.generate()

    assert result == WireGuardKeyPair(
        private_key="private_key",
        public_key="public_key",
    )

    assert executor.run.call_count == 2

    executor.run.assert_any_call(["wg", "genkey"])

    executor.run.assert_any_call(
        ["wg", "pubkey"],
        input_data="private_key",
    )
