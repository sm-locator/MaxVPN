#!/bin/sh
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

# MAXVPN_SHARED_ROUTE_LOCK_V1
# Based on the installed GL-MT5000 watchdog inspected 2026-11-21.
# Only mutation calls acquire the shared Smart Routing lock; never sleep with it.
ROUTE_LOCK=${MAXVPN_APPLIANCE_ROUTE_LOCK:-/opt/maxvpn-appliance/run/apply.lock}

with_routing_lock() (
    [ -x /usr/bin/flock ] || return 1
    [ -d "${ROUTE_LOCK%/*}" ] || return 1
    exec 9>>"$ROUTE_LOCK" || return 1
    /usr/bin/flock -x 9 || return 1
    # Check the route again after taking the lock. A concurrent deletion
    # may already have put LAN into WAN before the waiter acquires it.
    if [ "$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)" != "vless" ]; then
        /usr/bin/flock -u 9
        return 2
    fi
    "$@"
    result=$?
    # Do not leave a lock behind if an init script spawns a daemon that
    # unexpectedly inherits FD 9.
    /usr/bin/flock -u 9
    return "$result"
)

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
                if with_routing_lock "$VLESS_ON"; then
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
                    if with_routing_lock "$SING_BOX_INIT" "$SERVICE_ACTION"; then
                        wait_for_vless_components
                        wait_status=$?
                        if [ "$wait_status" -eq 0 ]; then
                            logger -t maxvpn-vless-watchdog "sing-box and maxvpn0 recovered"
                            if [ "$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)" = "vless" ]; then
                                if [ ! -x "$VLESS_ON" ]; then
                                    logger -t maxvpn-vless-watchdog "VLESS route helper is missing; fail-closed policy retained"
                                elif with_routing_lock "$VLESS_ON"; then
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
