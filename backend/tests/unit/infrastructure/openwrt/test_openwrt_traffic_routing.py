from unittest.mock import Mock

import pytest
from backend.infrastructure.openwrt.openwrt_traffic_routing import (
    OpenWrtTrafficRoutingService,
)
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
    TrafficAddressFamily,
    TrafficRoute,
    TrafficRoutingRule,
    TrafficTargetType,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


def make_executor() -> Mock:
    executor = Mock(spec=RemoteCommandExecutor)
    executor.run.return_value = Mock(
        returncode=0,
        stdout="",
        stderr="",
    )
    return executor


def make_policy() -> TrafficRoutingPolicy:
    return TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.1/32",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=200,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="10.0.0.0/8",
                action=TrafficRoute.VPN,
                priority=300,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="2001:db8::/32",
                action=TrafficRoute.DIRECT,
                priority=400,
                address_family=TrafficAddressFamily.IPV6,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="192.168.0.0/16",
                action=TrafficRoute.DIRECT,
                priority=500,
                enabled=False,
            ),
        ],
    )


def test_apply_uses_only_enabled_direct_cidr_rules() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    service.apply(make_policy())

    executor.run.assert_called_once()

    command = executor.run.call_args.args[0]

    assert command[:2] == ["sh", "-c"]

    script = command[2]

    assert "ipset add MAXVPN_DIRECT_STATIC 1.1.1.1/32" in script
    assert "10.0.0.0/8" not in script
    assert "example.com" not in script
    assert "2001:db8::/32" not in script
    assert "192.168.0.0/16" not in script


def test_apply_builds_expected_runtime_commands() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.1/32",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="8.8.8.0/24",
                action=TrafficRoute.DIRECT,
                priority=200,
            ),
        ],
    )

    service.apply(policy)

    command = executor.run.call_args.args[0]
    script = command[2]

    assert "ipset create MAXVPN_DIRECT_STATIC hash:ip" in script
    assert "ipset flush MAXVPN_DIRECT_STATIC" in script

    assert "iptables -t mangle -I PREROUTING 1" in script
    assert "-i br-lan" in script
    assert "-m set --match-set MAXVPN_DIRECT dst" in script
    assert "-j MARK --set-mark 0x64" in script

    assert "ip route flush table 200" in script
    assert ("ip route add table 200 default via 46.48.56.1 dev eth1") in script

    assert "ip rule del priority 100" in script
    assert ("ip rule add priority 100 fwmark 0x64/0xff table 200") in script

    assert "ipset add MAXVPN_DIRECT_STATIC 1.1.1.1/32" in script
    assert "ipset add MAXVPN_DIRECT_STATIC 8.8.8.0/24" in script


def test_apply_normalizes_cidr_networks() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.55/24",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
        ],
    )

    service.apply(policy)

    script = executor.run.call_args.args[0][2]

    assert "ipset add MAXVPN_DIRECT_STATIC 1.1.1.0/24" in script
    assert "1.1.1.55/24" not in script


def test_apply_raises_when_remote_command_fails() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="permission denied",
    )

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="OpenWrt traffic routing command failed",
    ):
        service.apply(make_policy())


def test_remove_builds_expected_cleanup_commands() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    service.remove()

    executor.run.assert_called_once()

    command = executor.run.call_args.args[0]

    assert command[:2] == ["sh", "-c"]

    script = command[2]

    assert "iptables -t mangle -D PREROUTING" in script
    assert "-i br-lan" in script
    assert "-m set --match-set MAXVPN_DIRECT dst" in script
    assert "ip rule del priority 100" in script
    assert "ip route flush table 200" in script
    assert "ipset destroy MAXVPN_DIRECT_STATIC" in script
    assert "ipset destroy MAXVPN_DIRECT 2>/dev/null" not in script
    assert "ip route flush cache" in script


def test_verify_returns_healthy_for_expected_runtime_state() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
                "Number of entries: 1\n"
                "Members:\n"
                "1.1.1.1\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "-P PREROUTING ACCEPT\n"
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-xmark 0x64/0xff\n"
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT_STATIC dst "
                "-j MARK --set-xmark 0x64/0xff\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=("default via 46.48.56.1 dev eth1\n"),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "0: from all lookup local\n"
                "100: from all fwmark 0x64/0xff lookup 200\n"
                "32766: from all lookup main\n"
            ),
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is True
    assert result.direct_ipset_exists is True
    assert result.direct_rule_count == 2
    assert result.routing_table_exists is True
    assert result.direct_route_exists is True
    assert result.reason is None


def test_verify_reports_missing_components() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=1,
            stdout="",
            stderr="missing",
        ),
        Mock(
            returncode=0,
            stdout="-P PREROUTING ACCEPT\n",
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="",
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="0: from all lookup local\n",
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is False
    assert result.direct_ipset_exists is False
    assert result.direct_rule_count == 0
    assert result.routing_table_exists is False
    assert result.direct_route_exists is False

    assert result.reason == (
        "traffic_routing_verification_failed: "
        "direct_ipset, "
        "static_ipset, "
        "direct_mangle_rule_count=0, "
        "static_mangle_rule_count=0, "
        "routing_table, "
        "direct_route, "
        "direct_fwmark_rule_count=0"
    )


def test_verify_accepts_legacy_mark_format() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-mark 0x64\n"
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT_STATIC dst "
                "-j MARK --set-mark 0x64\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=("default via 46.48.56.1 dev eth1\n"),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=("100: from all fwmark 0x64/0xff lookup 200\n"),
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is True
    assert result.direct_rule_count == 2
    assert result.reason is None


def test_verify_rejects_duplicate_mangle_rules() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-xmark 0x64/0xff\n"
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-xmark 0x64/0xff\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="default via 46.48.56.1 dev eth1\n",
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="100: from all fwmark 0x64/0xff lookup 200\n",
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is False
    assert result.direct_rule_count == 2
    assert "direct_mangle_rule_count=2" in (result.reason or "")


def test_verify_rejects_missing_mark_rule() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-xmark 0x64/0xff\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="default via 46.48.56.1 dev eth1\n",
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="0: from all lookup local\n",
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is False
    assert result.direct_rule_count == 1
    assert "direct_fwmark_rule_count=0" in (result.reason or "")


def test_verify_rejects_wrong_lan_interface() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "-A PREROUTING -i eth0 "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-xmark 0x64/0xff\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="default via 46.48.56.1 dev eth1\n",
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="100: from all fwmark 0x64/0xff lookup 200\n",
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is False
    assert result.direct_rule_count == 0
    assert "direct_mangle_rule_count=0" in (result.reason or "")


def test_verify_rejects_wrong_wan_route() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-xmark 0x64/0xff\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="default via 192.168.1.1 dev eth1\n",
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="100: from all fwmark 0x64/0xff lookup 200\n",
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is False
    assert result.direct_route_exists is False
    assert "direct_route" in (result.reason or "")


def test_verify_rejects_wrong_wan_interface() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "Name: MAXVPN_DIRECT_STATIC\n"
                "Type: hash:ip\n"
                "Header: family inet hashsize 1024 maxelem 65536\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "-A PREROUTING -i br-lan "
                "-m set --match-set MAXVPN_DIRECT dst "
                "-j MARK --set-xmark 0x64/0xff\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="default via 46.48.56.1 dev wlan0\n",
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="100: from all fwmark 0x64/0xff lookup 200\n",
            stderr="",
        ),
    ]

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    result = service.verify()

    assert result.healthy is False
    assert result.direct_route_exists is False
    assert "direct_route" in (result.reason or "")


def test_apply_installs_one_mangle_rule_per_direct_ipset() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.0/24",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="8.8.8.0/24",
                action=TrafficRoute.DIRECT,
                priority=200,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=300,
            ),
        ],
    )

    service.apply(policy)

    script = executor.run.call_args.args[0][2]

    assert script.count("iptables -t mangle -I PREROUTING 1") == 2

    insert_command = next(
        line
        for line in script.splitlines()
        if line.startswith("iptables -t mangle -I PREROUTING 1")
    )

    assert "-j MARK --set-mark 0x64" in insert_command
    assert "ipset add MAXVPN_DIRECT_STATIC 1.1.1.0/24" in script
    assert "ipset add MAXVPN_DIRECT_STATIC 8.8.8.0/24" in script
    assert "example.com" not in script


def test_apply_does_not_install_ipv6_into_ipv4_ipset() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="2001:db8::/32",
                action=TrafficRoute.DIRECT,
                priority=100,
                address_family=TrafficAddressFamily.IPV6,
            ),
        ],
    )

    service.apply(policy)

    script = executor.run.call_args.args[0][2]

    assert "ipset add MAXVPN_DIRECT" not in script
    assert "2001:db8::/32" not in script
    assert "ipset create MAXVPN_DIRECT_STATIC hash:ip family inet" in script


def test_remove_does_not_reference_awg_table_100() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    service.remove()

    script = executor.run.call_args.args[0][2]

    assert "table 100" not in script
    assert "table 200" in script
    assert "priority 100" in script


def test_apply_does_not_reference_awg_table_100() -> None:
    executor = make_executor()

    service = OpenWrtTrafficRoutingService(
        executor=executor,
    )

    service.apply(make_policy())

    script = executor.run.call_args.args[0][2]

    assert "table 100" not in script
    assert "table 200" in script
    assert "fwmark 0x64/0xff table 200" in script
