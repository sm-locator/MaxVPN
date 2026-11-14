from unittest.mock import Mock

import pytest
from backend.infrastructure.openwrt.openwrt_dnsmasq_routing import (
    OpenWrtDnsmasqRoutingService,
)
from backend.models.traffic_routing_policy import TrafficRoutingPolicy
from backend.models.traffic_routing_rule import (
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
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="Example.NET.",
                action=TrafficRoute.DIRECT,
                priority=90,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="vpn-only.example.org",
                action=TrafficRoute.VPN,
                priority=80,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.1/32",
                action=TrafficRoute.DIRECT,
                priority=70,
            ),
        ],
    )


def test_apply_builds_maxvpn_ipset_and_direct_domains() -> None:
    executor = make_executor()

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    service.apply(make_policy())

    assert executor.run.call_count == 1

    command = executor.run.call_args.args[0]

    assert command[:2] == ["sh", "-c"]

    script = command[2]

    assert "ipset flush MAXVPN_DIRECT" not in script
    assert "uci add dhcp ipset" in script
    assert 'uci add_list "$section.name=MAXVPN_DIRECT"' in script
    assert 'uci add_list "$section.domain=$domain"' in script
    assert "'example.com'" in script
    assert "'example.net'" in script
    assert "vpn-only.example.org" not in script
    assert "uci commit dhcp" in script
    assert "/etc/init.d/dnsmasq restart" in script


def test_build_apply_commands_creates_single_script() -> None:
    service = OpenWrtDnsmasqRoutingService(
        executor=make_executor(),
    )

    commands = service.build_apply_commands(
        [
            "example.com",
        ],
    )

    assert len(commands) == 1
    assert commands[0][0:2] == ["sh", "-c"]

    script = commands[0][2]

    assert "config ipset" not in script
    assert "uci add dhcp ipset" in script
    assert "new_section=$(uci add dhcp ipset)" in script
    assert 'section="dhcp.$new_section"' in script
    assert 'uci add_list "$section.name=MAXVPN_DIRECT"' in script
    assert "uci commit dhcp" in script
    assert "/etc/init.d/dnsmasq restart" in script


def test_apply_ignores_vpn_and_cidr_rules() -> None:
    executor = make_executor()

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="vpn.example.com",
                action=TrafficRoute.VPN,
                priority=100,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.CIDR,
                target="1.1.1.1/32",
                action=TrafficRoute.DIRECT,
                priority=90,
            ),
        ],
    )

    service.apply(policy)

    script = executor.run.call_args.args[0][2]

    assert 'uci add_list "$section.domain=' not in script
    assert "MAXVPN_DIRECT" in script
    assert "uci commit dhcp" in script
    assert "/etc/init.d/dnsmasq restart" in script


def test_verify_accepts_rendered_dnsmasq_mapping() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "dhcp.cfg096e2a=ipset\n"
                "dhcp.cfg096e2a.name='MAXVPN_DIRECT'\n"
                "dhcp.cfg096e2a.domain='example.com'\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout=(
                "/var/etc/dnsmasq.conf.cfg01411c:36:ipset=/example.com/MAXVPN_DIRECT\n"
            ),
            stderr="",
        ),
    ]

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    result = service.verify(
        ["example.com"],
    )

    assert result.healthy is True
    assert result.dnsmasq_section_exists is True
    assert result.direct_ipset_mapping_count == 1
    assert result.expected_domain_count == 1
    assert result.reason is None


def test_verify_accepts_real_dnsmasq_config_line() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "dhcp.cfg096e2a=ipset\n"
                "dhcp.cfg096e2a.name='MAXVPN_DIRECT'\n"
                "dhcp.cfg096e2a.domain='example.com'\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="ipset=/example.com/MAXVPN_DIRECT\n",
            stderr="",
        ),
    ]

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    result = service.verify(
        ["example.com"],
    )

    assert result.healthy is True
    assert result.dnsmasq_section_exists is True
    assert result.direct_ipset_mapping_count == 1
    assert result.expected_domain_count == 1
    assert result.reason is None


def test_verify_reports_missing_rendered_mapping() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "dhcp.cfg096e2a=ipset\n"
                "dhcp.cfg096e2a.name='MAXVPN_DIRECT'\n"
                "dhcp.cfg096e2a.domain='example.com'\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=1,
            stdout="",
            stderr="",
        ),
    ]

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    result = service.verify(
        ["example.com"],
    )

    assert result.healthy is False
    assert result.dnsmasq_section_exists is True
    assert result.direct_ipset_mapping_count == 1
    assert result.expected_domain_count == 1
    assert result.reason == (
        "dnsmasq_routing_verification_failed: missing_rendered_domains=example.com"
    )


def test_verify_reports_missing_maxvpn_section() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "dhcp.cfg123456=ipset\n"
                "dhcp.cfg123456.name='OTHER_SET'\n"
                "dhcp.cfg123456.domain='example.com'\n"
            ),
            stderr="",
        ),
    ]

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    result = service.verify(
        ["example.com"],
    )

    assert result.healthy is False
    assert result.dnsmasq_section_exists is False
    assert result.direct_ipset_mapping_count == 0
    assert result.expected_domain_count == 1
    assert result.reason == "maxvpn_ipset_section_missing"


def test_remove_removes_only_maxvpn_ipset_section() -> None:
    executor = make_executor()

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    service.remove()

    command = executor.run.call_args.args[0]

    assert command[:2] == ["sh", "-c"]

    script = command[2]

    assert "uci show dhcp" in script
    assert 'uci -q get "$candidate.name"' in script
    assert 'uci delete "$candidate"' in script
    assert "MAXVPN_DIRECT" in script
    assert "uci commit dhcp" in script
    assert "/etc/init.d/dnsmasq restart" in script


def test_domain_normalization() -> None:
    service = OpenWrtDnsmasqRoutingService(
        executor=make_executor(),
    )

    commands = service.build_apply_commands(
        [
            "  Example.COM. ",
        ],
    )

    script = commands[0][2]

    assert "'example.com'" in script


def test_wildcard_domain_is_normalized() -> None:
    service = OpenWrtDnsmasqRoutingService(
        executor=make_executor(),
    )

    commands = service.build_apply_commands(
        [
            "*.example.com",
        ],
    )

    script = commands[0][2]

    assert "'example.com'" in script


def test_invalid_domain_is_rejected() -> None:
    service = OpenWrtDnsmasqRoutingService(
        executor=make_executor(),
    )

    with pytest.raises(
        ValueError,
        match="at least two labels",
    ):
        service.build_apply_commands(
            [
                "localhost",
            ],
        )


def test_apply_raises_when_dnsmasq_command_fails() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.return_value = Mock(
        returncode=1,
        stdout="",
        stderr="permission denied",
    )

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    with pytest.raises(
        RuntimeError,
        match="dnsmasq routing command failed",
    ):
        service.apply(make_policy())

    executor.run.assert_called_once()


def test_apply_rejects_unsafe_overlapping_domain_rules() -> None:
    from backend.models.traffic_routing_policy import TrafficRoutingPolicy
    from backend.models.traffic_routing_rule import (
        TrafficRoute,
        TrafficRoutingRule,
        TrafficTargetType,
    )
    from backend.services.domain_routing_runtime_compiler import (
        DomainRoutingCompileError,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            ),
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="api.example.com",
                action=TrafficRoute.VPN,
                priority=200,
            ),
        ]
    )

    service = OpenWrtDnsmasqRoutingService(Mock())

    with pytest.raises(
        DomainRoutingCompileError,
        match="conflicting domain routing rules",
    ):
        service.apply(policy)


def test_extract_direct_domain_mappings_uses_runtime_compiler() -> None:
    from backend.models.traffic_routing_policy import TrafficRoutingPolicy
    from backend.models.traffic_routing_rule import (
        TrafficRoute,
        TrafficRoutingRule,
        TrafficTargetType,
    )
    from backend.services.domain_routing_runtime_compiler import (
        DomainRoutingRuntimeCompiler,
    )

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            )
        ]
    )

    compiler = Mock(spec=DomainRoutingRuntimeCompiler)
    compiler.compile.return_value = Mock(direct_domains=("example.com",))

    service = OpenWrtDnsmasqRoutingService(
        Mock(),
        compiler=compiler,
    )

    result = service._extract_direct_domain_mappings(policy)

    assert result == ("example.com",)
    compiler.compile.assert_called_once_with(policy)


def test_preview_builds_compiled_domain_commands_without_execution() -> None:
    from backend.models.traffic_routing_policy import TrafficRoutingPolicy
    from backend.models.traffic_routing_rule import (
        TrafficRoute,
        TrafficRoutingRule,
        TrafficTargetType,
    )

    executor = Mock()

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            )
        ]
    )

    service = OpenWrtDnsmasqRoutingService(executor)

    commands = service.preview(policy)

    assert len(commands) == 1
    assert commands[0][0:2] == ["sh", "-c"]

    script = commands[0][2]

    assert "MAXVPN_DIRECT" in script
    assert "example.com" in script
    assert "uci commit dhcp" in script
    assert "/etc/init.d/dnsmasq restart" in script

    executor.run.assert_not_called()


def test_preview_never_executes_remote_command() -> None:
    from backend.models.traffic_routing_policy import TrafficRoutingPolicy
    from backend.models.traffic_routing_rule import (
        TrafficRoute,
        TrafficRoutingRule,
        TrafficTargetType,
    )

    executor = Mock()

    policy = TrafficRoutingPolicy.from_rules(
        [
            TrafficRoutingRule(
                target_type=TrafficTargetType.DOMAIN,
                target="example.com",
                action=TrafficRoute.DIRECT,
                priority=100,
            )
        ]
    )

    service = OpenWrtDnsmasqRoutingService(executor)

    commands = service.preview(policy)

    assert commands
    executor.run.assert_not_called()


def test_verify_accepts_multiple_uci_domain_list_values() -> None:
    executor = Mock(spec=RemoteCommandExecutor)

    executor.run.side_effect = [
        Mock(
            returncode=0,
            stdout=(
                "dhcp.cfg096e2a=ipset\n"
                "dhcp.cfg096e2a.name='MAXVPN_DIRECT'\n"
                "dhcp.cfg096e2a.domain="
                "'2gis.ru' 'alfabank.ru' 'avito.ru'\n"
            ),
            stderr="",
        ),
        Mock(
            returncode=0,
            stdout="ipset=/2gis.ru/alfabank.ru/avito.ru/MAXVPN_DIRECT\n",
            stderr="",
        ),
    ]

    service = OpenWrtDnsmasqRoutingService(executor)

    result = service.verify(
        ["2gis.ru", "alfabank.ru", "avito.ru"],
    )

    assert result.healthy is True
    assert result.direct_ipset_mapping_count == 3
    assert result.expected_domain_count == 3
    assert result.reason is None


def test_apply_enables_maxvpn_dns_event_logging() -> None:
    executor = make_executor()

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    service.apply(make_policy())

    script = executor.run.call_args.args[0][2]

    assert "uci set dhcp.@dnsmasq[0].logqueries='1'" in script
    assert (
        "uci set dhcp.@dnsmasq[0].logfacility='/tmp/maxvpn-dns-events.log'"
    ) in script
    assert "rm -f /tmp/maxvpn-dns-events.log" not in script


def test_remove_disables_maxvpn_dns_event_logging() -> None:
    executor = make_executor()

    service = OpenWrtDnsmasqRoutingService(
        executor=executor,
    )

    service.remove()

    script = executor.run.call_args.args[0][2]

    assert "uci -q delete dhcp.@dnsmasq[0].logqueries" in script
    assert "uci -q delete dhcp.@dnsmasq[0].logfacility" in script
    assert "rm -f /tmp/maxvpn-dns-events.log" in script
