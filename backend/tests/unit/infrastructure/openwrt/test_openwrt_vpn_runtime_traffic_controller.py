from unittest.mock import Mock

import pytest
from backend.infrastructure.openwrt.openwrt_vpn_runtime_traffic_controller import (
    OpenWrtVpnRuntimeTrafficController,
)


def make_controller() -> tuple[
    OpenWrtVpnRuntimeTrafficController,
    Mock,
]:
    executor = Mock()

    executor.run.return_value = Mock(
        returncode=0,
        stderr="",
    )

    controller = OpenWrtVpnRuntimeTrafficController(executor)

    return controller, executor


def test_enable_vpn_mode() -> None:
    controller, executor = make_controller()

    controller.enable_vpn_mode()

    executor.run.assert_called_once_with(
        ["/usr/bin/vpn-lan-on"],
    )


def test_enable_wan_mode() -> None:
    controller, executor = make_controller()

    controller.enable_wan_mode()

    executor.run.assert_called_once_with(
        ["/usr/bin/vpn-lan-off"],
    )


def test_enable_vpn_mode_raises_on_command_failure() -> None:
    controller, executor = make_controller()

    executor.run.return_value = Mock(
        returncode=1,
        stderr="vpn-lan-on failed",
    )

    try:
        controller.enable_vpn_mode()
    except RuntimeError as exc:
        assert "returncode=1" in str(exc)
        assert "vpn-lan-on failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was not raised")


def test_enable_wan_mode_raises_on_command_failure() -> None:
    controller, executor = make_controller()

    executor.run.return_value = Mock(
        returncode=1,
        stderr="vpn-lan-off failed",
    )

    try:
        controller.enable_wan_mode()
    except RuntimeError as exc:
        assert "returncode=1" in str(exc)
        assert "vpn-lan-off failed" in str(exc)
    else:
        raise AssertionError("RuntimeError was not raised")


def test_get_mode_returns_vpn() -> None:
    controller, executor = make_controller()

    executor.run.return_value = Mock(
        returncode=0,
        stdout="vpn\n",
        stderr="",
    )

    result = controller.get_mode()

    executor.run.assert_called_once_with(
        ["cat", "/etc/maxvpn/runtime-mode"],
    )

    assert result == "vpn"


def test_enable_vless_mode_installs_support_before_switch() -> None:
    executor = Mock()
    executor.run.return_value = Mock(returncode=0, stdout="", stderr="")
    install_firewall = Mock()
    controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=install_firewall,
    )

    controller.enable_vless_mode()

    install_firewall.assert_called_once_with()
    executor.run.assert_called_once_with(["/usr/bin/vpn-lan-vless-on"])


def test_enable_vless_mode_requires_firewall_installer() -> None:
    controller, executor = make_controller()

    with pytest.raises(RuntimeError, match="firewall installer is missing"):
        controller.enable_vless_mode()

    executor.run.assert_not_called()


def test_get_mode_returns_wan() -> None:
    controller, executor = make_controller()

    executor.run.return_value = Mock(
        returncode=0,
        stdout="wan\n",
        stderr="",
    )

    result = controller.get_mode()

    executor.run.assert_called_once_with(
        ["cat", "/etc/maxvpn/runtime-mode"],
    )

    assert result == "wan"


def test_get_mode_returns_vless() -> None:
    controller, executor = make_controller()
    executor.run.return_value = Mock(
        returncode=0,
        stdout="vless\n",
        stderr="",
    )

    assert controller.get_mode() == "vless"


def test_get_mode_raises_on_command_failure() -> None:
    controller, executor = make_controller()

    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="cannot read runtime mode",
    )

    with pytest.raises(
        RuntimeError,
        match="OpenWrt VPN runtime traffic mode read failed",
    ):
        controller.get_mode()


def test_get_mode_raises_on_invalid_value() -> None:
    controller, executor = make_controller()

    executor.run.return_value = Mock(
        returncode=0,
        stdout="broken\n",
        stderr="",
    )

    with pytest.raises(
        RuntimeError,
        match="OpenWrt VPN runtime traffic mode is invalid",
    ):
        controller.get_mode()


def test_enable_vless_mode_does_not_switch_when_support_install_fails() -> None:
    executor = Mock()
    install_firewall = Mock(side_effect=RuntimeError("support install failed"))
    controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=install_firewall,
    )

    with pytest.raises(RuntimeError, match="support install failed"):
        controller.enable_vless_mode()

    install_firewall.assert_called_once_with()
    executor.run.assert_not_called()


def test_enable_vless_mode_starts_watchdog_after_helper() -> None:
    events = []
    executor = Mock()
    executor.run.side_effect = lambda command: (
        events.append(("helper", tuple(command)))
        or Mock(returncode=0, stdout="", stderr="")
    )

    controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=lambda: events.append(("install",)),
        firewall_watchdog_starter=lambda: events.append(("watchdog",)),
    )

    controller.enable_vless_mode()

    assert events == [
        ("install",),
        ("helper", ("/usr/bin/vpn-lan-vless-on",)),
        ("watchdog",),
    ]


def test_enable_vless_mode_starts_watchdog_after_helper_failure() -> None:
    events = []
    executor = Mock()
    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="VLESS policy verification failed",
    )

    controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=lambda: events.append(("install",)),
        firewall_watchdog_starter=lambda: events.append(("watchdog",)),
    )

    try:
        controller.enable_vless_mode()
    except RuntimeError as exc:
        assert "VLESS policy verification failed" in str(exc)
    else:
        raise AssertionError("expected VLESS activation failure")

    assert events == [("install",), ("watchdog",)]
    executor.run.assert_called_once_with(["/usr/bin/vpn-lan-vless-on"])


def test_enable_vless_mode_keeps_activation_success_when_watchdog_start_fails() -> None:
    executor = Mock()
    executor.run.return_value = Mock(returncode=0, stdout="", stderr="")

    def fail_watchdog_start() -> None:
        raise RuntimeError("watchdog start failed")

    controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=lambda: None,
        firewall_watchdog_starter=fail_watchdog_start,
    )

    warning = controller.enable_vless_mode()

    assert warning is not None
    assert "VLESS watchdog failed to start" in warning
    assert "watchdog start failed" in warning
    executor.run.assert_called_once_with(["/usr/bin/vpn-lan-vless-on"])


def test_enable_vless_mode_warns_when_watchdog_starter_is_not_configured() -> None:
    executor = Mock()
    executor.run.return_value = Mock(returncode=0, stdout="", stderr="")
    controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=lambda: None,
    )

    warning = controller.enable_vless_mode()

    assert warning == "VLESS watchdog starter is not configured"
    executor.run.assert_called_once_with(["/usr/bin/vpn-lan-vless-on"])


def test_enable_vless_mode_reports_helper_and_watchdog_start_failures() -> None:
    executor = Mock()
    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="helper failed",
    )

    def fail_watchdog_start() -> None:
        raise RuntimeError("watchdog start failed")

    controller = OpenWrtVpnRuntimeTrafficController(
        executor,
        firewall_installer=lambda: None,
        firewall_watchdog_starter=fail_watchdog_start,
    )

    try:
        controller.enable_vless_mode()
    except RuntimeError as exc:
        assert "activation failed" in str(exc)
        assert "helper failed" in str(exc)
        assert "watchdog start failed" in str(exc)
    else:
        raise AssertionError("expected activation and watchdog start failure")
