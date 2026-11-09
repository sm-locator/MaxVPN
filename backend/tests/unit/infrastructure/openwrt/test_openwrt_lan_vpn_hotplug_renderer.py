from backend.infrastructure.openwrt.openwrt_lan_vpn_hotplug_renderer import (
    OpenWrtLanVpnHotplugRenderer,
)


def test_render_contains_runtime_mode() -> None:
    script = OpenWrtLanVpnHotplugRenderer().render()

    assert "RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode" in script
    assert 'mode="$(get_runtime_mode)"' in script


def test_render_adds_vless_default_and_dns_policy_rules() -> None:
    script = OpenWrtLanVpnHotplugRenderer().render()

    assert "VLESS_IF=maxvpn0" in script
    assert 'elif [ "$mode" = "vless" ]' in script
    assert 'ip route add default dev "$VLESS_IF" table "$TABLE"' in script
    assert 'ip rule add to "$DNS_IP/32" lookup "$TABLE"' in script
    assert "ifup:maxvpn0" in script


def test_render_only_adds_vpn_rule_in_vpn_mode() -> None:
    script = OpenWrtLanVpnHotplugRenderer().render()

    assert 'if [ "$mode" = "vpn" ]' in script
    assert 'ip rule add iif "$LAN_IF" lookup "$TABLE"' in script


def test_render_removes_rule_before_rebuild() -> None:
    script = OpenWrtLanVpnHotplugRenderer().render()

    assert 'ip rule del priority "$PRIORITY"' in script


def test_render_adds_default_route_only_when_vpn_is_up() -> None:
    script = OpenWrtLanVpnHotplugRenderer().render()

    assert "grep -q 'UP'" in script
    assert 'ip route add default dev "$VPN_IF" table "$TABLE"' in script
