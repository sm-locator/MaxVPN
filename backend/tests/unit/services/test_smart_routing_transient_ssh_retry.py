from __future__ import annotations

import json
from pathlib import Path

import pytest
from backend.models.command_result import CommandResult
from backend.services.smart_routing_sync import (
    SmartRoutingSyncError,
    SmartRoutingSyncService,
)


class SequenceExecutor:
    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.commands: list[list[str]] = []

    def run(self, command: list[str], stdin: str | None = None) -> CommandResult:
        del stdin
        self.commands.append(command)
        if not self.results:
            raise AssertionError("executor was called more times than expected")
        return self.results.pop(0)


def _service(tmp_path: Path, executor: SequenceExecutor) -> SmartRoutingSyncService:
    domains = tmp_path / "russia-direct.txt"
    domains.write_text("", encoding="utf-8")
    return SmartRoutingSyncService(
        executor=executor,
        russian_direct_file=domains,
    )


def test_smart_routing_read_retries_transient_ssh_close_once(tmp_path: Path) -> None:
    executor = SequenceExecutor(
        [
            CommandResult(
                stdout="",
                stderr="Connection closed by 192.168.8.1 port 22",
                returncode=255,
            ),
            CommandResult(
                stdout=json.dumps({"rules": [], "runtime": {}}),
                stderr="",
                returncode=0,
            ),
        ]
    )

    state = _service(tmp_path, executor).fetch_remote_state()

    assert len(executor.commands) == 2
    assert state["rules"] == []
    assert state["runtime"] == {}


def test_smart_routing_read_does_not_retry_non_transport_error(tmp_path: Path) -> None:
    executor = SequenceExecutor(
        [
            CommandResult(
                stdout="",
                stderr="curl: (22) The requested URL returned error: 500",
                returncode=22,
            ),
        ]
    )

    with pytest.raises(SmartRoutingSyncError, match="brume_routing_read_failed"):
        _service(tmp_path, executor).fetch_remote_state()

    assert len(executor.commands) == 1


def test_vless_selection_history_retries_transient_ssh_close() -> None:
    from backend.infrastructure.openwrt.openwrt_vless_singbox_controller import (
        OpenWrtVlessSingBoxController,
    )

    payload = {
        "monitor": {"enabled": True, "last_error": None},
        "current": None,
        "events": [],
    }
    executor = SequenceExecutor(
        [
            CommandResult(
                stdout="",
                stderr="Connection closed by 192.168.8.1 port 22",
                returncode=255,
            ),
            CommandResult(
                stdout=json.dumps(payload),
                stderr="",
                returncode=0,
            ),
        ]
    )

    result = OpenWrtVlessSingBoxController(executor).selection_history()

    assert result == payload
    assert len(executor.commands) == 2


def test_vless_selection_history_does_not_retry_non_transport_error() -> None:
    from backend.infrastructure.openwrt.openwrt_vless_singbox_controller import (
        OpenWrtVlessSingBoxController,
    )

    executor = SequenceExecutor(
        [
            CommandResult(
                stdout="",
                stderr="curl: (22) The requested URL returned error: 500",
                returncode=22,
            ),
        ]
    )

    with pytest.raises(RuntimeError, match="Unable to read VLESS selection history"):
        OpenWrtVlessSingBoxController(executor).selection_history()

    assert len(executor.commands) == 1
