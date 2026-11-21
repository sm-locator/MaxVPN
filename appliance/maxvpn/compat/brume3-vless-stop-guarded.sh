#!/bin/sh
# GL-MT5000 CN candidate: fail-closed sing-box stop helper for MaxVPN.
# This helper is called by VlessControl.stop() while its routing flock is held.
# Never use it to switch LAN modes, rewrite firewall rules or stop watchdog.
set -eu

MODE_FILE=/etc/maxvpn/runtime-mode
SERVICE=/etc/init.d/maxvpn-sing-box

[ -r "$MODE_FILE" ] || { echo "MaxVPN runtime mode missing" >&2; exit 1; }
[ -x "$SERVICE" ] || { echo "sing-box init service missing" >&2; exit 1; }
MODE="$(cat "$MODE_FILE")"

case "$MODE" in
    vless)
        echo "Refusing to stop sing-box while LAN routes through VLESS; select WAN or protected VPN first" >&2
        exit 1
        ;;
    vpn)
        # Stopping sing-box is permitted only with an intact WireGuard LAN route.
        ip rule show | grep -q '1000:.*iif br-lan.*lookup 100' || {
            echo "Protected VPN LAN routing rule missing" >&2; exit 1;
        }
        ip route show table 100 | grep -q '^default dev WireGuard' || {
            echo "Protected VPN LAN route not confirmed" >&2; exit 1;
        }
        ;;
    wan)
        # An explicitly selected WAN route is already allowed by the operator.
        # Do not mask inconsistent mode/routing by stopping the live TUN.
        if ip rule show | grep -q '1000:.*iif br-lan.*lookup 100'; then
            echo "LAN is still policy routed; refusing sing-box stop" >&2
            exit 1
        fi
        ;;
    *)
        echo "Unknown MaxVPN LAN traffic mode" >&2
        exit 1
        ;;
esac

# A concurrent mode change caused by a manual shell command is unsupported.
[ "$(cat "$MODE_FILE")" = "$MODE" ] || {
    echo "MaxVPN mode changed during stop preflight" >&2
    exit 1
}

if pidof sing-box >/dev/null 2>&1; then
    "$SERVICE" stop || exit 1
    sleep 1
    if pidof sing-box >/dev/null 2>&1; then
        echo "sing-box still running" >&2
        exit 1
    fi
fi
echo "SINGBOX_STOP_SAFE"
exit 0
