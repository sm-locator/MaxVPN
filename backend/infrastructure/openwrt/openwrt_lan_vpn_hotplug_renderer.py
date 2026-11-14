from __future__ import annotations


class OpenWrtLanVpnHotplugRenderer:
    PATH = "/etc/hotplug.d/iface/99-lan-vpn"

    def render(self) -> str:
        return """#!/bin/sh

TABLE=100
PRIORITY=1000
LAN_IF=br-lan
VPN_IF=WireGuard
VLESS_IF=maxvpn0
RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode

get_runtime_mode() {
    mode=vpn

    if [ -f "$RUNTIME_MODE_FILE" ]; then
        mode="$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)"
    fi

    case "$mode" in
        wan|vpn|vless) ;;
        *) mode=vpn ;;
    esac

    echo "$mode"
}

apply_lan_vpn_policy() {
    ip rule del priority "$PRIORITY" 2>/dev/null || true
    for DNS_IP in 1.1.1.1 8.8.8.8 9.9.9.9; do
        ip rule del to "$DNS_IP/32" lookup "$TABLE" priority 200 2>/dev/null || true
    done

    ip route flush table "$TABLE"

    ip route show table main | while IFS= read -r route; do
        case "$route" in
            default\\ *|"")
                continue
                ;;
        esac

        ip route add $route table "$TABLE" 2>/dev/null || true
    done

    mode="$(get_runtime_mode)"

    if [ "$mode" = "vpn" ] &&
       ip link show "$VPN_IF" 2>/dev/null | grep -q 'UP'
    then
        ip route add default dev "$VPN_IF" table "$TABLE" 2>/dev/null || true
        ip rule add iif "$LAN_IF" lookup "$TABLE" \
            priority "$PRIORITY" 2>/dev/null || true
    elif [ "$mode" = "vless" ] &&
         ip link show "$VLESS_IF" 2>/dev/null | grep -q 'UP'
    then
        ip route add default dev "$VLESS_IF" table "$TABLE" 2>/dev/null || true
        ip rule add iif "$LAN_IF" lookup "$TABLE" \
            priority "$PRIORITY" 2>/dev/null || true
        # Router DNS uses TUN; sing-box bootstrap DNS stays DIRECT.
        for DNS_IP in 1.1.1.1 8.8.8.8 9.9.9.9; do
            ip rule add to "$DNS_IP/32" lookup "$TABLE" \
                priority 200 2>/dev/null || true
        done
    fi
}

schedule_vless_restore() {
    (
        attempt=0
        while [ "$attempt" -lt 45 ]; do
            [ "$(get_runtime_mode)" = "vless" ] || exit 0
            if ip link show "$VLESS_IF" 2>/dev/null | grep -q 'UP'; then
                ACTION=ifup INTERFACE=maxvpn0 "$0" >/dev/null 2>&1
                exit $?
            fi
            sleep 1
            attempt=$((attempt + 1))
        done
    ) >/dev/null 2>&1 &
}

case "$ACTION:$INTERFACE" in
    ifup:WireGuard|ifup:maxvpn0|ifup:br-lan|ifup:wan|ifdown:WireGuard|ifdown:maxvpn0|ifdown:br-lan|ifdown:wan)
        apply_lan_vpn_policy
        ;;
esac

# Netifd may bring WAN/LAN up before sing-box creates maxvpn0.
case "$ACTION:$INTERFACE" in
    ifup:br-lan|ifup:wan)
        [ "$(get_runtime_mode)" = "vless" ] && schedule_vless_restore
        ;;
esac

exit 0
"""
