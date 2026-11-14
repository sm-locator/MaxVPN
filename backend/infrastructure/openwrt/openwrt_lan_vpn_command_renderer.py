# ruff: noqa: E501
from __future__ import annotations


class OpenWrtLanVpnCommandRenderer:
    """
    Renders the standalone Brume LAN VPN toggle scripts.
    """

    RUNTIME_MODE_FILE = "/etc/maxvpn/runtime-mode"
    HOTPLUG = "/etc/hotplug.d/iface/99-lan-vpn"
    FIREWALL = "/etc/maxvpn/firewall.user"
    VPN_LAN_OFF = "/usr/bin/vpn-lan-off"
    VLESS_SERVICE = "/etc/init.d/maxvpn-sing-box"
    VLESS_STOP = "/usr/bin/vpn-lan-vless-stop"

    LAN_INTERFACE = "br-lan"
    VPN_INTERFACE = "WireGuard"
    ROUTING_TABLE = 100
    RULE_PRIORITY = 1000
    VLESS_INTERFACE = "maxvpn0"
    IPV4_TRANSITION_GUARD = "MAXVPN_MODE_TRANSITION_GUARD"
    IPV6_TRANSITION_GUARD = "MAXVPN6_MODE_GUARD"

    def _render_runtime_lock(self) -> str:
        return """RUNTIME_LOCK_FILE=/tmp/maxvpn-runtime.lock
if [ "${MAXVPN_RUNTIME_LOCK_HELD:-0}" = "1" ]; then
    if ! ( : >&9 ) 2>/dev/null; then
        echo "MaxVPN runtime lock marker exists without inherited lock descriptor" >&2
        exit 1
    fi
else
    command -v flock >/dev/null 2>&1 || {
        echo "flock is required for serialized MaxVPN runtime changes" >&2
        exit 1
    }
    umask 077
    exec 9>"$RUNTIME_LOCK_FILE" || {
        echo "Unable to open MaxVPN runtime lock file" >&2
        exit 1
    }
    flock -x 9 || {
        echo "Unable to acquire MaxVPN runtime lock" >&2
        exit 1
    }
    export MAXVPN_RUNTIME_LOCK_HELD=1
fi
"""

    def _render_transition_guard_functions(self) -> str:
        functions = """ensure_transition_guards() {
    iptables -N __IPV4_GUARD__ 2>/dev/null || true
    if ! iptables -C __IPV4_GUARD__ -i "$LAN_IF" -o "$WAN_IF" -j DROP 2>/dev/null; then
        iptables -A __IPV4_GUARD__ -i "$LAN_IF" -o "$WAN_IF" -j DROP || return 1
    fi
    if [ "$(iptables -S forwarding_rule 1 2>/dev/null || true)" != "-A forwarding_rule -j __IPV4_GUARD__" ]; then
        iptables -I forwarding_rule 1 -j __IPV4_GUARD__ || return 1
    fi
    iptables -C forwarding_rule -j __IPV4_GUARD__ 2>/dev/null || return 1

    ip6tables -N __IPV6_GUARD__ 2>/dev/null || true
    if ! ip6tables -C __IPV6_GUARD__ -i "$LAN_IF" -o "$WAN_IF" -j DROP 2>/dev/null; then
        ip6tables -A __IPV6_GUARD__ -i "$LAN_IF" -o "$WAN_IF" -j DROP || return 1
    fi
    if [ "$(ip6tables -S forwarding_rule 1 2>/dev/null || true)" != "-A forwarding_rule -j __IPV6_GUARD__" ]; then
        ip6tables -I forwarding_rule 1 -j __IPV6_GUARD__ || return 1
    fi
    ip6tables -C forwarding_rule -j __IPV6_GUARD__ 2>/dev/null || return 1
    return 0
}

read_vpn_routes() {
    if TABLE_100_ROUTES="$(LC_ALL=C ip route show table 100 2>&1)"; then
        return 0
    fi
    # iproute2 reports a table that has never been populated as missing.
    case "$TABLE_100_ROUTES" in
        'Error: ipv4: FIB table does not exist.'|'Error: ipv4: FIB table does not exist.
Dump terminated')
            TABLE_100_ROUTES=
            return 0
            ;;
    esac
    return 1
}

remove_one_transition_guard() {
    FAMILY="$1"
    CHAIN="$2"

    # Preflight the complete table before detaching anything. A failed
    # inspection must leave the active guard jump untouched.
    RULES="$($FAMILY -S 2>/dev/null)" || {
        echo "Unable to inspect firewall rules while removing $CHAIN" >&2
        return 1
    }
    if ! printf '%s\n' "$RULES" | grep -F -x -e "-N $CHAIN" >/dev/null 2>&1; then
        if printf '%s\n' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" >/dev/null 2>&1; then
            echo "$CHAIN is referenced but its chain definition is missing" >&2
            return 1
        fi
        return 0
    fi

    # Only canonical references from the global OpenWrt forwarding hook are
    # safe to remove here. Keep every guard attached on unexpected references.
    if printf '%s\n' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" | grep -F -v -x -e "-A forwarding_rule -j $CHAIN" -e "-A forwarding_rule -g $CHAIN" >/dev/null 2>&1; then
        echo "$CHAIN has a non-standard firewall reference; refusing cleanup" >&2
        return 1
    fi

    # Remove all duplicate jump/goto entries; repeated runs are idempotent.
    while "$FAMILY" -D forwarding_rule -j "$CHAIN" 2>/dev/null; do :; done
    while "$FAMILY" -D forwarding_rule -g "$CHAIN" 2>/dev/null; do :; done

    RULES="$($FAMILY -S 2>/dev/null)" || {
        echo "Unable to verify firewall references for $CHAIN" >&2
        return 1
    }
    if printf '%s\n' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" >/dev/null 2>&1; then
        echo "$CHAIN is still referenced by a firewall rule" >&2
        return 1
    fi

    "$FAMILY" -F "$CHAIN" || return 1
    "$FAMILY" -X "$CHAIN" || return 1

    RULES="$($FAMILY -S 2>/dev/null)" || {
        echo "Unable to verify firewall cleanup for $CHAIN" >&2
        return 1
    }
    if printf '%s\n' "$RULES" | grep -F -x -e "-N $CHAIN" >/dev/null 2>&1; then
        echo "$CHAIN still exists after cleanup" >&2
        return 1
    fi
    if printf '%s\n' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" >/dev/null 2>&1; then
        echo "$CHAIN is still referenced after cleanup" >&2
        return 1
    fi
    return 0
}

remove_transition_guards() {
    remove_one_transition_guard iptables __IPV4_GUARD__ || return 1
    remove_one_transition_guard ip6tables __IPV6_GUARD__ || return 1
    return 0
}
"""
        return functions.replace("__IPV4_GUARD__", self.IPV4_TRANSITION_GUARD).replace(
            "__IPV6_GUARD__", self.IPV6_TRANSITION_GUARD
        )

    def render_on(self) -> str:
        script = """#!/bin/sh
set -eu

RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode
HOTPLUG=/etc/hotplug.d/iface/99-lan-vpn
FIREWALL=/etc/maxvpn/firewall.user
LAN_IF=br-lan
WAN_IF=eth1

__RUNTIME_LOCK__
__TRANSITION_GUARD_FUNCTIONS__

# Install IPv4 and IPv6 WAN guards before changing the runtime mode.
ensure_transition_guards || {
    echo "Unable to install temporary WAN transition guards" >&2
    exit 1
}

printf '%s\\n' vpn > "$RUNTIME_MODE_FILE"

# Apply fail-closed VPN firewall policy before attempting to start WireGuard.
"$FIREWALL" >/dev/null 2>&1 || {
    echo "VPN firewall activation failed; WAN transition guards retained" >&2
    exit 1
}

# firewall.user also has its own short-lived update guards. Reconfirm that
# the longer mode-transition guards remain attached while routes are built.
ensure_transition_guards || {
    echo "Unable to maintain WAN transition guards" >&2
    exit 1
}

if ! ifstatus WireGuard 2>/dev/null | grep -q '"up": true'; then
    ifup WireGuard >/dev/null 2>&1 || {
        echo "WireGuard failed to start; WAN remains fail-closed" >&2
        exit 1
    }
fi

sleep 1
ACTION=ifup INTERFACE=WireGuard "$HOTPLUG" >/dev/null 2>&1 || {
    echo "WireGuard route hotplug failed; WAN remains fail-closed" >&2
    exit 1
}

ip route flush cache 2>/dev/null || true

iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o WireGuard -j ACCEPT 2>/dev/null || {
    echo "WireGuard IPv4 firewall rule verification failed; WAN remains fail-closed" >&2
    exit 1
}
iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o "$WAN_IF" -m mark --mark 0x64/0xff -j ACCEPT 2>/dev/null || {
    echo "DIRECT IPv4 firewall rule verification failed; WAN remains fail-closed" >&2
    exit 1
}
iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o "$WAN_IF" -j DROP 2>/dev/null || {
    echo "VPN WAN fail-closed rule verification failed; WAN remains fail-closed" >&2
    exit 1
}
ip6tables -C MAXVPN_LAN6_FORWARD -i "$LAN_IF" -o WireGuard -j ACCEPT 2>/dev/null || {
    echo "WireGuard IPv6 firewall rule verification failed; WAN remains fail-closed" >&2
    exit 1
}
ip6tables -C MAXVPN_LAN6_FORWARD -i "$LAN_IF" -o "$WAN_IF" -j DROP 2>/dev/null || {
    echo "VPN IPv6 WAN fail-closed rule verification failed; WAN remains fail-closed" >&2
    exit 1
}
iptables -C forwarding_rule -j MAXVPN_LAN_FORWARD 2>/dev/null || {
    echo "IPv4 firewall chain attachment verification failed; WAN remains fail-closed" >&2
    exit 1
}
ip6tables -C forwarding_rule -j MAXVPN_LAN6_FORWARD 2>/dev/null || {
    echo "IPv6 firewall chain attachment verification failed; WAN remains fail-closed" >&2
    exit 1
}
iptables -t nat -C MAXVPN_DIRECT_NAT -o "$WAN_IF" -m mark --mark 0x64/0xff -j MASQUERADE 2>/dev/null || {
    echo "DIRECT NAT rule verification failed; WAN remains fail-closed" >&2
    exit 1
}
iptables -t nat -C POSTROUTING -j MAXVPN_DIRECT_NAT 2>/dev/null || {
    echo "DIRECT NAT chain attachment verification failed; WAN remains fail-closed" >&2
    exit 1
}

ip rule show | grep -q '1000:.*iif br-lan.*lookup 100' || {
    echo "WireGuard LAN policy rule verification failed; WAN remains fail-closed" >&2
    exit 1
}
if ! read_vpn_routes || ! printf '%s\\n' "$TABLE_100_ROUTES" | grep -q '^default dev WireGuard'; then
    echo "WireGuard default route verification failed; WAN remains fail-closed" >&2
    exit 1
fi

remove_transition_guards || {
    echo "WireGuard routes are active, but transition guards could not be removed" >&2
    exit 1
}

echo "VPN LAN: ON (WireGuard route verified; marked DIRECT IPv4 retained; IPv6 firewall verified)"
exit 0
"""
        script = script.replace("__RUNTIME_LOCK__", self._render_runtime_lock())
        return script.replace(
            "__TRANSITION_GUARD_FUNCTIONS__",
            self._render_transition_guard_functions(),
        )

    def render_vless_stop(self) -> str:
        return (
            "#!/bin/sh\nset -eu\n\n"
            f"RUNTIME_MODE_FILE={self.RUNTIME_MODE_FILE}\n"
            f"WAN_SWITCH={self.VPN_LAN_OFF}\n"
            f"VLESS_SERVICE={self.VLESS_SERVICE}\n\n"
            + self._render_runtime_lock()
            + r"""
PREVIOUS_MODE="$(cat "$RUNTIME_MODE_FILE")"
case "$PREVIOUS_MODE" in
    vless)
        "$WAN_SWITCH" >/dev/null
        [ "$(cat "$RUNTIME_MODE_FILE")" = wan ] || {
            echo "WAN transition could not be verified; refusing to stop sing-box" >&2
            exit 1
        }
        ;;
    vpn|wan) ;;
    *) echo "Invalid MaxVPN runtime mode; refusing to stop sing-box" >&2; exit 1 ;;
esac

if [ -x "$VLESS_SERVICE" ]; then
    if "$VLESS_SERVICE" running 9>&- >/dev/null; then
        "$VLESS_SERVICE" stop 9>&- >/dev/null
    fi
    "$VLESS_SERVICE" disable 9>&- >/dev/null
    if "$VLESS_SERVICE" running 9>&- >/dev/null; then
        echo "sing-box still reports a running procd instance" >&2
        exit 1
    fi
fi

printf '%s\n' "$PREVIOUS_MODE"
"""
        )

    def render_vless_on(self) -> str:
        script = """#!/bin/sh
set -u

RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode
HOTPLUG=/etc/hotplug.d/iface/99-lan-vpn
FIREWALL=/etc/maxvpn/firewall.user
SING_BOX=/usr/bin/sing-box
SING_BOX_CONFIG=/etc/maxvpn/sing-box-vless.json
VLESS_IF=maxvpn0
VLESS_SERVICE=__VLESS_SERVICE__

__RUNTIME_LOCK__

# Refuse activation unless the validated sing-box configuration and TUN exist.
[ -x "$SING_BOX" ] || { echo "sing-box binary is missing" >&2; exit 1; }
"$SING_BOX" check -c "$SING_BOX_CONFIG" >/dev/null 2>&1 || {
    echo "sing-box configuration check failed" >&2
    exit 1
}
# A stopped managed service may still have a terminating process.
if [ -x "$VLESS_SERVICE" ] && ! "$VLESS_SERVICE" running 9>&- >/dev/null; then
    echo "sing-box service is not running" >&2
    exit 1
fi
pidof sing-box >/dev/null 2>&1 || {
    echo "sing-box process is not running" >&2
    exit 1
}
ip link show "$VLESS_IF" 2>/dev/null | grep -q 'UP' || {
    echo "VLESS TUN interface is not up" >&2
    exit 1
}
[ -x "$FIREWALL" ] || { echo "MaxVPN firewall script is missing" >&2; exit 1; }
[ -x "$HOTPLUG" ] || { echo "MaxVPN hotplug script is missing" >&2; exit 1; }

PREVIOUS_MODE=wan
if [ -f "$RUNTIME_MODE_FILE" ]; then
    PREVIOUS_MODE="$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)"
fi
case "$PREVIOUS_MODE" in
    wan|vpn|vless) ;;
    *) echo "Invalid previous MaxVPN mode" >&2; exit 1 ;;
esac

# Watchdog/boot restore may only repair policy if VLESS is still the selected
# mode after this process acquired the shared runtime lock.
if [ "${MAXVPN_EXPECT_RUNTIME_MODE:-}" = "vless" ] && [ "$PREVIOUS_MODE" != "vless" ]; then
    echo "Runtime mode changed before VLESS repair acquired the lock; refusing stale repair" >&2
    exit 2
fi

LAN_IF=br-lan
WAN_IF=eth1
__TRANSITION_GUARD_FUNCTIONS__
ensure_transition_guards || {
    echo "Unable to install temporary WAN transition guards" >&2
    exit 1
}

verify_previous_mode() {
    grep -q "^$PREVIOUS_MODE$" "$RUNTIME_MODE_FILE" || return 1
    iptables -C forwarding_rule -j MAXVPN_LAN_FORWARD 2>/dev/null || return 1
    ip6tables -C forwarding_rule -j MAXVPN_LAN6_FORWARD 2>/dev/null || return 1
    iptables -t nat -C MAXVPN_DIRECT_NAT -o "$WAN_IF" -m mark --mark 0x64/0xff -j MASQUERADE 2>/dev/null || return 1
    iptables -t nat -C POSTROUTING -j MAXVPN_DIRECT_NAT 2>/dev/null || return 1

    IP_RULES="$(ip rule show)" || return 1
    read_vpn_routes || return 1
    case "$PREVIOUS_MODE" in
        wan)
            iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT 2>/dev/null || return 1
            ip6tables -C MAXVPN_LAN6_FORWARD -i "$LAN_IF" -o "$WAN_IF" -j ACCEPT 2>/dev/null || return 1
            if printf '%s\\n' "$IP_RULES" | grep -Eq 'lookup 100([[:space:]]|$)'; then
                return 1
            fi
            [ -z "$TABLE_100_ROUTES" ] || return 1
            ;;
        vpn)
            if ! ifstatus WireGuard 2>/dev/null | grep -q '"up": true'; then
                return 1
            fi
            iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o WireGuard -j ACCEPT 2>/dev/null || return 1
            iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o "$WAN_IF" -m mark --mark 0x64/0xff -j ACCEPT 2>/dev/null || return 1
            iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o "$WAN_IF" -j DROP 2>/dev/null || return 1
            ip6tables -C MAXVPN_LAN6_FORWARD -i "$LAN_IF" -o WireGuard -j ACCEPT 2>/dev/null || return 1
            ip6tables -C MAXVPN_LAN6_FORWARD -i "$LAN_IF" -o "$WAN_IF" -j DROP 2>/dev/null || return 1
            printf '%s\\n' "$IP_RULES" | grep -q '1000:.*iif br-lan.*lookup 100' || return 1
            printf '%s\\n' "$TABLE_100_ROUTES" | grep -q '^default dev WireGuard' || return 1
            ;;
        vless)
            ip link show maxvpn0 2>/dev/null | grep -q 'UP' || return 1
            iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o maxvpn0 -j ACCEPT 2>/dev/null || return 1
            iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o "$WAN_IF" -m mark --mark 0x64/0xff -j ACCEPT 2>/dev/null || return 1
            iptables -C MAXVPN_LAN_FORWARD -i "$LAN_IF" -o "$WAN_IF" -j DROP 2>/dev/null || return 1
            ip6tables -C MAXVPN_LAN6_FORWARD -i "$LAN_IF" -j DROP 2>/dev/null || return 1
            printf '%s\\n' "$IP_RULES" | grep -q '1000:.*iif br-lan.*lookup 100' || return 1
            printf '%s\\n' "$TABLE_100_ROUTES" | grep -q '^default dev maxvpn0' || return 1
            for DNS_IP in 1.1.1.1 8.8.8.8 9.9.9.9; do
                printf '%s\\n' "$IP_RULES" | grep -Fq "to $DNS_IP lookup 100" || return 1
            done
            ;;
        *)
            return 1
            ;;
    esac

    return 0
}

rollback_previous_mode() {
    printf '%s\\n' "$PREVIOUS_MODE" > "$RUNTIME_MODE_FILE" || return 1
    "$FIREWALL" >/dev/null 2>&1 || return 1
    ACTION=ifup INTERFACE=br-lan "$HOTPLUG" >/dev/null 2>&1 || return 1
    verify_previous_mode || return 1
    # Release the transition guards only after the previous policy is restored
    # and independently verified. On any rollback error they remain fail-closed.
    remove_transition_guards || return 1
    return 0
}

printf '%s\\n' vless > "$RUNTIME_MODE_FILE" || {
    if rollback_previous_mode; then
        echo "Unable to persist VLESS runtime mode; previous policy restored" >&2
    else
        echo "Unable to persist VLESS runtime mode; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
}
if ! "$FIREWALL" >/dev/null 2>&1; then
    if rollback_previous_mode; then
        echo "VLESS firewall activation failed; previous mode restored" >&2
    else
        echo "VLESS firewall activation failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi

if ! ACTION=ifup INTERFACE=maxvpn0 "$HOTPLUG" >/dev/null 2>&1; then
    if rollback_previous_mode; then
        echo "VLESS route activation failed; previous mode restored" >&2
    else
        echo "VLESS route activation failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
ip route flush cache 2>/dev/null || true

if ! iptables -C MAXVPN_LAN_FORWARD -i br-lan -o maxvpn0 -j ACCEPT 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS IPv4 TUN firewall rule verification failed; previous mode restored" >&2
    else
        echo "VLESS IPv4 TUN firewall rule verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! iptables -C MAXVPN_LAN_FORWARD -i br-lan -o eth1 -m mark --mark 0x64/0xff -j ACCEPT 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS DIRECT firewall rule verification failed; previous mode restored" >&2
    else
        echo "VLESS DIRECT firewall rule verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! iptables -C MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS WAN fail-closed firewall rule verification failed; previous mode restored" >&2
    else
        echo "VLESS WAN fail-closed firewall rule verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! ip6tables -C MAXVPN_LAN6_FORWARD -i br-lan -j DROP 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS IPv6 fail-closed firewall rule verification failed; previous mode restored" >&2
    else
        echo "VLESS IPv6 fail-closed firewall rule verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! iptables -C forwarding_rule -j MAXVPN_LAN_FORWARD 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS IPv4 firewall chain attachment verification failed; previous mode restored" >&2
    else
        echo "VLESS IPv4 firewall chain attachment verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! ip6tables -C forwarding_rule -j MAXVPN_LAN6_FORWARD 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS IPv6 firewall chain attachment verification failed; previous mode restored" >&2
    else
        echo "VLESS IPv6 firewall chain attachment verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi

if ! ip rule show | grep -q '1000:.*iif br-lan.*lookup 100'; then
    if rollback_previous_mode; then
        echo "VLESS LAN policy rule verification failed; previous mode restored" >&2
    else
        echo "VLESS LAN policy rule verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! read_vpn_routes || ! printf '%s\\n' "$TABLE_100_ROUTES" | grep -q '^default dev maxvpn0'; then
    if rollback_previous_mode; then
        echo "VLESS default route verification failed; previous mode restored" >&2
    else
        echo "VLESS default route verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! grep -q '^vless$' "$RUNTIME_MODE_FILE"; then
    if rollback_previous_mode; then
        echo "VLESS runtime mode verification failed; previous mode restored" >&2
    else
        echo "VLESS runtime mode verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi

if ! iptables -t nat -C MAXVPN_DIRECT_NAT -o eth1 -m mark --mark 0x64/0xff -j MASQUERADE 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS DIRECT NAT rule verification failed; previous mode restored" >&2
    else
        echo "VLESS DIRECT NAT rule verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi
if ! iptables -t nat -C POSTROUTING -j MAXVPN_DIRECT_NAT 2>/dev/null; then
    if rollback_previous_mode; then
        echo "VLESS DIRECT NAT chain attachment verification failed; previous mode restored" >&2
    else
        echo "VLESS DIRECT NAT chain attachment verification failed; rollback incomplete, transition guards retained" >&2
    fi
    exit 1
fi

remove_transition_guards || {
    echo "VLESS routes are active, but transition guards could not be removed" >&2
    exit 1
}

echo "VLESS LAN: ON (IPv4 through maxvpn0; DIRECT IPv4 retained; IPv6 blocked)"
exit 0
"""
        script = script.replace("__VLESS_SERVICE__", self.VLESS_SERVICE)
        script = script.replace("__RUNTIME_LOCK__", self._render_runtime_lock())
        return script.replace(
            "__TRANSITION_GUARD_FUNCTIONS__",
            self._render_transition_guard_functions(),
        )

    def render_vless_restore_init(self) -> str:
        """Render a late boot hook that restores LAN policy only in VLESS mode."""
        return """#!/bin/sh /etc/rc.common

START=99
STOP=10

RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode
VLESS_ON=/usr/bin/vpn-lan-vless-on
SING_BOX=/usr/bin/sing-box
SING_BOX_CONFIG=/etc/maxvpn/sing-box-vless.json
VLESS_IF=maxvpn0

start() {
    [ -f "$RUNTIME_MODE_FILE" ] || return 0
    mode="$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)"
    [ "$mode" = "vless" ] || return 0

    if [ ! -x "$VLESS_ON" ]; then
        logger -t maxvpn-vless-restore "VLESS restore helper missing; keeping fail-closed policy"
        return 1
    fi

    # sing-box is started by its own S95 service. Wait for the process and TUN.
    attempt=0
    while [ "$attempt" -lt 90 ]; do
        mode="$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)"
        [ "$mode" = "vless" ] || return 0

        if [ -x "$SING_BOX" ] && [ -r "$SING_BOX_CONFIG" ] &&
           "$SING_BOX" check -c "$SING_BOX_CONFIG" >/dev/null 2>&1 &&
           pidof sing-box >/dev/null 2>&1 &&
           ip link show "$VLESS_IF" 2>/dev/null | grep -q 'UP'; then
            tries=0
            while [ "$tries" -lt 3 ]; do
                mode="$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)"
                [ "$mode" = "vless" ] || return 0
                if MAXVPN_EXPECT_RUNTIME_MODE=vless "$VLESS_ON"; then
                    logger -t maxvpn-vless-restore "VLESS LAN routes restored after boot"
                    return 0
                fi
                tries=$((tries + 1))
                sleep 2
            done
            logger -t maxvpn-vless-restore "VLESS route restore failed; keeping fail-closed policy"
            return 1
        fi

        sleep 1
        attempt=$((attempt + 1))
    done

    logger -t maxvpn-vless-restore "Timed out waiting for sing-box/maxvpn0; keeping fail-closed policy"
    return 1
}

stop() {
    return 0
}
"""

    def render_vless_watchdog(self) -> str:
        """Render a watchdog that restores the VLESS service and LAN policy."""
        return """#!/bin/sh
set -u

RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode
VLESS_ON=/usr/bin/vpn-lan-vless-on
SING_BOX=/usr/bin/sing-box
SING_BOX_CONFIG=/etc/maxvpn/sing-box-vless.json
SING_BOX_INIT=/etc/init.d/maxvpn-sing-box
VLESS_IF=maxvpn0
FAILURE_THRESHOLD=3
RESTART_COOLDOWN_TICKS=6
POLICY_REPAIR_COOLDOWN_TICKS=6
unhealthy_ticks=0
restart_cooldown=0
policy_repair_cooldown=0

policy_is_healthy() {
    ip rule show | grep -q '1000:.*iif br-lan.*lookup 100' || return 1
    ip route show table 100 | grep -q '^default dev maxvpn0' || return 1
    for DNS_IP in 1.1.1.1 8.8.8.8 9.9.9.9; do
        ip rule show | grep -Fq "to $DNS_IP lookup 100" || return 1
    done
    iptables -C MAXVPN_LAN_FORWARD -i br-lan -o maxvpn0 -j ACCEPT 2>/dev/null || return 1
    iptables -C MAXVPN_LAN_FORWARD -i br-lan -o eth1 -m mark --mark 0x64/0xff -j ACCEPT 2>/dev/null || return 1
    iptables -C MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j DROP 2>/dev/null || return 1
    ip6tables -C MAXVPN_LAN6_FORWARD -i br-lan -j DROP 2>/dev/null || return 1
    iptables -C forwarding_rule -j MAXVPN_LAN_FORWARD 2>/dev/null || return 1
    ip6tables -C forwarding_rule -j MAXVPN_LAN6_FORWARD 2>/dev/null || return 1
    return 0
}

vless_components_healthy() {
    [ -x "$SING_BOX" ] || return 1
    [ -r "$SING_BOX_CONFIG" ] || return 1
    "$SING_BOX" check -c "$SING_BOX_CONFIG" >/dev/null 2>&1 || return 1
    pidof sing-box >/dev/null 2>&1 || return 1
    ip link show "$VLESS_IF" 2>/dev/null | grep -q 'UP' || return 1
    return 0
}

wait_for_vless_components() {
    attempt=0
    while [ "$attempt" -lt 20 ]; do
        [ "$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)" = "vless" ] || return 2
        if vless_components_healthy; then
            return 0
        fi
        sleep 1
        attempt=$((attempt + 1))
    done
    return 1
}

while :; do
    if [ "$restart_cooldown" -gt 0 ]; then
        restart_cooldown=$((restart_cooldown - 1))
    fi
    if [ "$policy_repair_cooldown" -gt 0 ]; then
        policy_repair_cooldown=$((policy_repair_cooldown - 1))
    fi

    mode="$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)"
    if [ "$mode" != "vless" ]; then
        unhealthy_ticks=0
        policy_repair_cooldown=0
        sleep 5
        continue
    fi

    if vless_components_healthy; then
        unhealthy_ticks=0
        if ! policy_is_healthy; then
            if [ "$policy_repair_cooldown" -gt 0 ]; then
                :
            elif [ ! -x "$VLESS_ON" ]; then
                logger -t maxvpn-vless-watchdog "VLESS policy incomplete but repair helper is unavailable; fail-closed policy retained"
                policy_repair_cooldown=$POLICY_REPAIR_COOLDOWN_TICKS
            elif [ "$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)" = "vless" ]; then
                logger -t maxvpn-vless-watchdog "VLESS policy incomplete; attempting repair"
                if MAXVPN_EXPECT_RUNTIME_MODE=vless "$VLESS_ON"; then
                    logger -t maxvpn-vless-watchdog "VLESS policy repaired"
                    policy_repair_cooldown=0
                else
                    logger -t maxvpn-vless-watchdog "VLESS policy repair failed; fail-closed policy retained"
                    policy_repair_cooldown=$POLICY_REPAIR_COOLDOWN_TICKS
                fi
            fi
        else
            policy_repair_cooldown=0
        fi
    else
        unhealthy_ticks=$((unhealthy_ticks + 1))
        if [ "$unhealthy_ticks" -ge "$FAILURE_THRESHOLD" ] && [ "$restart_cooldown" -eq 0 ]; then
            # A few consecutive failed checks avoid racing normal procd respawn.
            if [ "$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)" = "vless" ]; then
                if [ ! -x "$SING_BOX" ] || [ ! -r "$SING_BOX_CONFIG" ]; then
                    logger -t maxvpn-vless-watchdog "sing-box binary/config unavailable; cannot recover VLESS TUN; fail-closed policy retained"
                    restart_cooldown=$RESTART_COOLDOWN_TICKS
                elif ! "$SING_BOX" check -c "$SING_BOX_CONFIG" >/dev/null 2>&1; then
                    logger -t maxvpn-vless-watchdog "sing-box config check failed; refusing restart; fail-closed policy retained"
                    restart_cooldown=$RESTART_COOLDOWN_TICKS
                elif [ ! -x "$SING_BOX_INIT" ]; then
                    logger -t maxvpn-vless-watchdog "sing-box init service missing; cannot recover VLESS TUN; fail-closed policy retained"
                    restart_cooldown=$RESTART_COOLDOWN_TICKS
                else
                    # Do not call rc.common "restart" when the process is already
                    # gone: restart executes stop first, which can produce
                    # "Command failed: Not found" for an absent procd instance.
                    # Start an absent process; restart only when sing-box is still
                    # running but maxvpn0 (or another checked component) is unhealthy.
                    if pidof sing-box >/dev/null 2>&1; then
                        SERVICE_ACTION=restart
                    else
                        SERVICE_ACTION=start
                    fi
                    logger -t maxvpn-vless-watchdog "VLESS components unhealthy; attempting $SERVICE_ACTION of maxvpn-sing-box"
                    if "$SING_BOX_INIT" "$SERVICE_ACTION"; then
                        wait_for_vless_components
                        wait_status=$?
                        if [ "$wait_status" -eq 0 ]; then
                            logger -t maxvpn-vless-watchdog "sing-box and maxvpn0 recovered"
                            if [ "$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)" = "vless" ]; then
                                if [ ! -x "$VLESS_ON" ]; then
                                    logger -t maxvpn-vless-watchdog "VLESS route helper is missing; fail-closed policy retained"
                                elif MAXVPN_EXPECT_RUNTIME_MODE=vless "$VLESS_ON"; then
                                    logger -t maxvpn-vless-watchdog "VLESS LAN policy restored after service recovery"
                                else
                                    logger -t maxvpn-vless-watchdog "VLESS LAN policy restore failed; fail-closed policy retained"
                                    sleep 10
                                fi
                            fi
                        elif [ "$wait_status" -eq 2 ]; then
                            logger -t maxvpn-vless-watchdog "runtime mode changed during recovery; skipping VLESS policy restore"
                        else
                            logger -t maxvpn-vless-watchdog "sing-box $SERVICE_ACTION did not restore maxvpn0 within 20 seconds; fail-closed policy retained"
                        fi
                    else
                        logger -t maxvpn-vless-watchdog "maxvpn-sing-box $SERVICE_ACTION command failed; fail-closed policy retained"
                    fi
                    restart_cooldown=$RESTART_COOLDOWN_TICKS
                fi
            fi
            unhealthy_ticks=0
        fi
    fi

    sleep 5
done
"""

    def render_vless_watchdog_init(self) -> str:
        """Render procd supervision for the persistent VLESS watchdog."""
        return """#!/bin/sh /etc/rc.common

START=99
STOP=10
USE_PROCD=1

WATCHDOG=/usr/bin/maxvpn-vless-watchdog

start_service() {
    [ -x "$WATCHDOG" ] || {
        logger -t maxvpn-vless-watchdog "watchdog script is missing"
        return 1
    }
    procd_open_instance
    procd_set_param command "$WATCHDOG"
    procd_set_param respawn 3600 5 5
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
"""

    def render_off(self) -> str:
        script = """#!/bin/sh
set -eu


RUNTIME_MODE_FILE=/etc/maxvpn/runtime-mode

FIREWALL=/etc/maxvpn/firewall.user
LAN_IF=br-lan
WAN_IF=eth1

__RUNTIME_LOCK__

__TRANSITION_GUARD_FUNCTIONS__

# Block LAN-to-WAN forwarding before changing routes, mode or firewall policy.
ensure_transition_guards || {
    echo "Unable to install temporary WAN transition guards; runtime mode was not changed" >&2
    exit 1
}

# Switch firewall policy to direct WAN first.

printf '%s\\n' wan > "$RUNTIME_MODE_FILE"



# Remove LAN policy routing.

ip rule del priority 1000 2>/dev/null || true

for DNS_IP in 1.1.1.1 8.8.8.8 9.9.9.9; do
    ip rule del to "$DNS_IP/32" lookup 100 priority 200 2>/dev/null || true
done

ip route flush table 100 2>/dev/null || true

ip route flush cache 2>/dev/null || true



# Apply WAN firewall policy.

"$FIREWALL" >/dev/null 2>&1 || exit 1



# Stop WireGuard while the transition guards still block WAN traffic.

WG_STATUS="$(ifstatus WireGuard 2>/dev/null)" || {
    # Accept absence only after all three inventories were read successfully.
    WG_CONFIG="$(uci show network)" &&
    WG_OBJECTS="$(ubus list 'network.interface.*')" &&
    WG_LINKS="$(ip -o link show)" || {
        echo "Unable to inspect network inventory; transition guards retained" >&2
        exit 1
    }

    if printf '%s\\n' "$WG_CONFIG" | grep -q '^network\\.WireGuard[.=]' ||
       printf '%s\\n' "$WG_OBJECTS" | grep -qx 'network.interface.WireGuard' ||
       printf '%s\\n' "$WG_LINKS" | grep -Eq '^[0-9]+: WireGuard(@[^:]+)?:'
    then
        echo "WireGuard exists but status is unavailable; transition guards retained" >&2
        exit 1
    fi

    WG_STATUS='{"up": false}'
    echo "WireGuard absent: shutdown not required"
}

if printf '%s\\n' "$WG_STATUS" | grep -q '"up": true'; then
    # ifdown may return non-zero after the interface has already gone down;
    # verify the resulting state instead of trusting its exit status alone.
    ifdown WireGuard >/dev/null 2>&1 || true

    WG_STATUS="$(ifstatus WireGuard 2>/dev/null)" || {
        echo "Unable to verify WireGuard shutdown; transition guards retained" >&2
        exit 1
    }
    if printf '%s\\n' "$WG_STATUS" | grep -q '"up": true'; then
        echo "WireGuard remains up after ifdown; transition guards retained" >&2
        exit 1
    fi
fi



# Remove any rule/default route that could have been recreated

# during the WireGuard shutdown event.

ip rule del priority 1000 2>/dev/null || true

for DNS_IP in 1.1.1.1 8.8.8.8 9.9.9.9; do
    ip rule del to "$DNS_IP/32" lookup 100 priority 200 2>/dev/null || true
done

ip route flush table 100 2>/dev/null || true

ip route flush cache 2>/dev/null || true



# Re-apply WAN firewall after interface shutdown.

"$FIREWALL" >/dev/null 2>&1 || exit 1



# Final verification.

IP_RULES="$(ip rule show)" || {
    echo "Unable to inspect IP policy rules; transition guards retained" >&2
    exit 1
}

if printf '%s\\n' "$IP_RULES" | grep -Eq 'lookup 100([[:space:]]|$)'; then
    echo "IP policy rules still reference VPN routing table 100; transition guards retained" >&2
    exit 1
fi



read_vpn_routes || {
    echo "Unable to inspect routing table 100; transition guards retained" >&2
    exit 1
}

if [ -n "$TABLE_100_ROUTES" ]; then
    echo "Routes remain in VPN routing table 100; transition guards retained" >&2
    exit 1
fi



if ! grep -q '^wan$' "$RUNTIME_MODE_FILE"; then
    echo "VPN LAN: FAILED"
    exit 1
fi

# Do not expose WAN until the final WAN policy is verifiably installed.
iptables -C MAXVPN_LAN_FORWARD -i br-lan -o eth1 -j ACCEPT 2>/dev/null || {
    echo "WAN IPv4 allow rule verification failed; transition guards retained" >&2
    exit 1
}
ip6tables -C MAXVPN_LAN6_FORWARD -i br-lan -o eth1 -j ACCEPT 2>/dev/null || {
    echo "WAN IPv6 allow rule verification failed; transition guards retained" >&2
    exit 1
}
iptables -C forwarding_rule -j MAXVPN_LAN_FORWARD 2>/dev/null || {
    echo "IPv4 firewall chain attachment verification failed; transition guards retained" >&2
    exit 1
}
ip6tables -C forwarding_rule -j MAXVPN_LAN6_FORWARD 2>/dev/null || {
    echo "IPv6 firewall chain attachment verification failed; transition guards retained" >&2
    exit 1
}

remove_transition_guards || {
    echo "WAN policy is active, but transition guards could not be removed" >&2
    exit 1
}

echo "VPN LAN: OFF"
exit 0
"""
        script = script.replace("__RUNTIME_LOCK__", self._render_runtime_lock())
        return script.replace(
            "__TRANSITION_GUARD_FUNCTIONS__",
            self._render_transition_guard_functions(),
        )
