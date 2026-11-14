from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from backend.infrastructure.openwrt import (
    openwrt_vless_singbox_controller as controller_module,
)


class _SequenceExecutor:
    def __init__(self, results: list[SimpleNamespace]) -> None:
        self.results = list(results)
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> SimpleNamespace:
        self.commands.append(command)
        return self.results.pop(0)


def _result(
    returncode: int,
    stdout: str = "",
    stderr: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _make_controller(executor: _SequenceExecutor):
    controller_type = next(
        candidate
        for candidate in vars(controller_module).values()
        if isinstance(candidate, type)
        and candidate.__module__ == controller_module.__name__
        and callable(getattr(candidate, "read_appliance_vless_store", None))
    )
    instance = object.__new__(controller_type)
    instance._executor = executor
    return instance


def test_appliance_store_retries_transient_ssh_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module.time, "sleep", lambda _: None)
    executor = _SequenceExecutor(
        [
            _result(
                255,
                stderr="Connection closed by 192.168.8.1 port 22",
            ),
            _result(0, stdout='{"profiles": []}'),
        ]
    )
    controller = _make_controller(executor)

    assert controller.read_appliance_vless_store() == {"profiles": []}
    assert len(executor.commands) == 2


def test_appliance_store_does_not_retry_non_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module.time, "sleep", lambda _: None)
    executor = _SequenceExecutor([_result(1, stderr="cat: profile store not found")])
    controller = _make_controller(executor)

    with pytest.raises(RuntimeError, match="Unable to read VLESS profiles"):
        controller.read_appliance_vless_store()

    assert len(executor.commands) == 1


def test_appliance_store_retries_at_most_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module.time, "sleep", lambda _: None)
    executor = _SequenceExecutor(
        [
            _result(255, stderr="Connection closed by remote host"),
            _result(255, stderr="Connection reset by peer"),
        ]
    )
    controller = _make_controller(executor)

    with pytest.raises(RuntimeError, match="Unable to read VLESS profiles"):
        controller.read_appliance_vless_store()

    assert len(executor.commands) == 2


def test_sing_box_status_retries_transient_ssh_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module.time, "sleep", lambda _: None)
    executor = _SequenceExecutor(
        [
            _result(
                255,
                stderr="Connection closed by 192.168.8.1 port 22",
            ),
            _result(
                0,
                stdout=json.dumps(
                    {
                        "maxvpn-sing-box": {
                            "instances": {
                                "main": {"running": True},
                            }
                        }
                    }
                ),
            ),
        ]
    )
    controller = _make_controller(executor)
    payload = json.dumps(
        {controller.SERVICE_NAME: {"instances": {"main": {"running": True}}}}
    )
    executor.results[1] = _result(0, stdout=payload)

    assert controller.status()["running"] is True
    assert len(executor.commands) == 2


def test_sing_box_status_does_not_retry_non_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module.time, "sleep", lambda _: None)
    executor = _SequenceExecutor([_result(1, stderr="ubus: method not found")])
    controller = _make_controller(executor)

    with pytest.raises(RuntimeError, match="Reading sing-box service status failed"):
        controller.status()

    assert len(executor.commands) == 1


def test_sing_box_status_retries_at_most_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(controller_module.time, "sleep", lambda _: None)
    executor = _SequenceExecutor(
        [
            _result(255, stderr="Connection closed by remote host"),
            _result(255, stderr="Connection reset by peer"),
        ]
    )
    controller = _make_controller(executor)

    with pytest.raises(RuntimeError, match="Reading sing-box service status failed"):
        controller.status()

    assert len(executor.commands) == 2


def test_vpn_runtime_mode_retries_transient_ssh_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from backend.infrastructure.openwrt import (
        openwrt_vpn_runtime_traffic_controller as mode_module,
    )

    monkeypatch.setattr(mode_module.time, "sleep", lambda _: None)

    class Executor:
        def __init__(self) -> None:
            self.results = [
                SimpleNamespace(
                    returncode=255,
                    stdout="",
                    stderr="Connection closed by 192.168.8.1 port 22",
                ),
                SimpleNamespace(
                    returncode=0,
                    stdout="vless",
                    stderr="",
                ),
            ]
            self.commands = []

        def run(self, command):
            self.commands.append(command)
            return self.results.pop(0)

    executor = Executor()
    controller = object.__new__(mode_module.OpenWrtVpnRuntimeTrafficController)
    controller._executor = executor

    assert controller.get_mode() == "vless"
    assert len(executor.commands) == 2


def test_vpn_runtime_mode_does_not_retry_non_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from backend.infrastructure.openwrt import (
        openwrt_vpn_runtime_traffic_controller as mode_module,
    )

    monkeypatch.setattr(mode_module.time, "sleep", lambda _: None)

    class Executor:
        def __init__(self) -> None:
            self.calls = 0

        def run(self, command):
            self.calls += 1
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="permission denied",
            )

    executor = Executor()
    controller = object.__new__(mode_module.OpenWrtVpnRuntimeTrafficController)
    controller._executor = executor

    with pytest.raises(
        RuntimeError, match="OpenWrt VPN runtime traffic mode read failed"
    ):
        controller.get_mode()

    assert executor.calls == 1
