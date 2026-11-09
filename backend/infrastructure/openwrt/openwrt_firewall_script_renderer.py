# ruff: noqa: E501
from __future__ import annotations

from backend.infrastructure.openwrt.openwrt_lan_vpn_command_renderer import (
    OpenWrtLanVpnCommandRenderer,
)
from backend.models.vpn_traffic_policy import VpnTrafficPolicy


class OpenWrtFirewallScriptRenderer:
    """
    Renders a persistent OpenWrt firewall.user script for MaxVPN.

    Normal LAN traffic is fail-closed to WAN.
    Traffic explicitly marked by MaxVPN Smart Routing is allowed
    to leave through the WAN interface.
    """

    IPV4_CHAIN = "MAXVPN_LAN_FORWARD"
    IPV6_CHAIN = "MAXVPN_LAN6_FORWARD"
    IPV4_NAT_CHAIN = "MAXVPN_DIRECT_NAT"
    IPV4_UPDATE_GUARD_CHAIN = "MAXVPN_FIREWALL_UPDATE_GUARD"
    IPV6_UPDATE_GUARD_CHAIN = "MAXVPN6_FIREWALL_UPDATE_GUARD"

    FORWARD_RULE_CHAIN = "forwarding_rule"

    DIRECT_MARK = "0x64/0xff"

    def render(self, policy: VpnTrafficPolicy) -> str:
        lines = [
            "#!/bin/sh",
            "",
            "# MaxVPN runtime firewall policy.",
            "# This script is executed by /etc/firewall.user.",
            "",
            "set -eu",
            "",
            'RUNTIME_LOCK_FILE="/tmp/maxvpn-runtime.lock"',
            'if [ "${MAXVPN_RUNTIME_LOCK_HELD:-0}" = "1" ]; then',
            "    if ! ( : >&9 ) 2>/dev/null; then",
            '        echo "MaxVPN runtime lock marker exists without inherited lock descriptor" >&2',
            "        exit 1",
            "    fi",
            "else",
            '    command -v flock >/dev/null 2>&1 || { echo "flock is required for serialized MaxVPN runtime changes" >&2; exit 1; }',
            "    umask 077",
            '    exec 9>"$RUNTIME_LOCK_FILE" || { echo "Unable to open MaxVPN runtime lock file" >&2; exit 1; }',
            '    flock -x 9 || { echo "Unable to acquire MaxVPN runtime lock" >&2; exit 1; }',
            "    export MAXVPN_RUNTIME_LOCK_HELD=1",
            "fi",
            "",
            'RUNTIME_MODE_FILE="/etc/maxvpn/runtime-mode"',
            'RUNTIME_MODE="vpn"',
            '[ -f "$RUNTIME_MODE_FILE" ] && '
            'RUNTIME_MODE="$(cat "$RUNTIME_MODE_FILE" 2>/dev/null || true)"',
            '[ "$RUNTIME_MODE" = "wan" ] || [ "$RUNTIME_MODE" = "vless" ] || RUNTIME_MODE="vpn"',  # noqa: E501
            "",
        ]

        # Protect LAN-to-WAN forwarding while the active chains are rebuilt.
        # If any mutation fails, set -e aborts and the temporary guards remain.
        lines.extend(self._render_update_guards(policy))
        lines.append("")

        lines.extend(
            self._render_family(
                binary="iptables",
                chain=self.IPV4_CHAIN,
                policy=policy,
            ),
        )

        lines.append("")

        lines.extend(
            self._render_direct_nat(
                policy=policy,
            ),
        )

        lines.append("")

        lines.extend(
            self._render_family(
                binary="ip6tables",
                chain=self.IPV6_CHAIN,
                policy=policy,
            ),
        )

        # Detach update guards only after IPv4, IPv6 and DIRECT NAT are ready.
        lines.extend(self._render_update_guards_cleanup())

        lines.extend(
            [
                "",
                "exit 0",
                "",
            ],
        )

        return "\n".join(lines)

    def _render_update_guards(self, policy: VpnTrafficPolicy) -> list[str]:
        ipv4 = self.IPV4_UPDATE_GUARD_CHAIN
        ipv6 = self.IPV6_UPDATE_GUARD_CHAIN
        lan = policy.lan_interface
        wan = policy.wan_interface

        return [
            f"iptables -N {ipv4} 2>/dev/null || true",
            f"if ! iptables -C {ipv4} -i {lan} -o {wan} -j DROP 2>/dev/null; then",
            f"    iptables -A {ipv4} -i {lan} -o {wan} -j DROP",
            "fi",
            f'if [ "$(iptables -S {self.FORWARD_RULE_CHAIN} 1 2>/dev/null || true)" != "-A {self.FORWARD_RULE_CHAIN} -j {ipv4}" ]; then',
            f"    iptables -I {self.FORWARD_RULE_CHAIN} 1 -j {ipv4}",
            "fi",
            f"ip6tables -N {ipv6} 2>/dev/null || true",
            f"if ! ip6tables -C {ipv6} -i {lan} -o {wan} -j DROP 2>/dev/null; then",
            f"    ip6tables -A {ipv6} -i {lan} -o {wan} -j DROP",
            "fi",
            f'if [ "$(ip6tables -S {self.FORWARD_RULE_CHAIN} 1 2>/dev/null || true)" != "-A {self.FORWARD_RULE_CHAIN} -j {ipv6}" ]; then',
            f"    ip6tables -I {self.FORWARD_RULE_CHAIN} 1 -j {ipv6}",
            "fi",
        ]

    def _render_update_guards_cleanup(self) -> list[str]:
        ipv4 = self.IPV4_UPDATE_GUARD_CHAIN
        ipv6 = self.IPV6_UPDATE_GUARD_CHAIN

        return [
            "remove_update_guard() {",
            '    FAMILY="$1"',
            '    CHAIN="$2"',
            '    RULES="$("$FAMILY" -S 2>/dev/null)" || { echo "Unable to inspect firewall while removing $CHAIN" >&2; return 1; }',
            '    if ! printf \'%s\\n\' "$RULES" | grep -F -x -e "-N $CHAIN" >/dev/null 2>&1; then',
            '        if printf \'%s\\n\' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" >/dev/null 2>&1; then',
            '            echo "$CHAIN is referenced but its chain definition is missing" >&2',
            "            return 1",
            "        fi",
            "        return 0",
            "    fi",
            '    if printf \'%s\\n\' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" | grep -F -v -x -e "-A forwarding_rule -j $CHAIN" -e "-A forwarding_rule -g $CHAIN" >/dev/null 2>&1; then',
            '        echo "$CHAIN has a non-standard firewall reference; refusing cleanup" >&2',
            "        return 1",
            "    fi",
            '    while "$FAMILY" -D forwarding_rule -j "$CHAIN" 2>/dev/null; do :; done',
            '    while "$FAMILY" -D forwarding_rule -g "$CHAIN" 2>/dev/null; do :; done',
            '    RULES="$("$FAMILY" -S 2>/dev/null)" || { echo "Unable to verify firewall references for $CHAIN" >&2; return 1; }',
            '    if printf \'%s\\n\' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" >/dev/null 2>&1; then',
            '        echo "$CHAIN is still referenced by a firewall rule" >&2',
            "        return 1",
            "    fi",
            '    "$FAMILY" -F "$CHAIN" || return 1',
            '    "$FAMILY" -X "$CHAIN" || return 1',
            '    RULES="$("$FAMILY" -S 2>/dev/null)" || { echo "Unable to verify firewall cleanup for $CHAIN" >&2; return 1; }',
            '    if printf \'%s\\n\' "$RULES" | grep -F -x -e "-N $CHAIN" >/dev/null 2>&1 || printf \'%s\\n\' "$RULES" | grep -F -e "-j $CHAIN" -e "-g $CHAIN" >/dev/null 2>&1; then',
            '        echo "$CHAIN remains after cleanup" >&2',
            "        return 1",
            "    fi",
            "    return 0",
            "}",
            f"remove_update_guard iptables {ipv4}",
            f"remove_update_guard ip6tables {ipv6}",
        ]

    def _render_family(
        self,
        *,
        binary: str,
        chain: str,
        policy: VpnTrafficPolicy,
    ) -> list[str]:
        forward_chain = self.FORWARD_RULE_CHAIN
        mode_guard = (
            OpenWrtLanVpnCommandRenderer.IPV4_TRANSITION_GUARD
            if binary == "iptables"
            else OpenWrtLanVpnCommandRenderer.IPV6_TRANSITION_GUARD
        )
        mode_jump = f"-A {forward_chain} -j {mode_guard}"
        lines = [
            f"{binary} -N {chain} 2>/dev/null || true",
            f"{binary} -F {chain}",
        ]

        if binary == "iptables":
            lines.extend(
                [
                    'if [ "$RUNTIME_MODE" = "wan" ]; then',
                    (
                        f"{binary} -A {chain} "
                        f"-i {policy.lan_interface} "
                        f"-o {policy.wan_interface} "
                        "-j ACCEPT"
                    ),
                    'elif [ "$RUNTIME_MODE" = "vless" ]; then',
                    (
                        f"{binary} -A {chain} "
                        f"-i {policy.lan_interface} -o maxvpn0 -j ACCEPT"
                    ),
                    (
                        f"{binary} -A {chain} "
                        f"-i {policy.lan_interface} -o {policy.wan_interface} "
                        f"-m mark --mark {self.DIRECT_MARK} -j ACCEPT"
                    ),
                    (
                        f"{binary} -A {chain} "
                        f"-i {policy.lan_interface} -o {policy.wan_interface} -j DROP"
                    ),
                    "else",
                ]
            )
        elif binary == "ip6tables":
            lines.extend(
                [
                    'if [ "$RUNTIME_MODE" = "vless" ]; then',
                    (f"{binary} -A {chain} -i {policy.lan_interface} -j DROP"),
                    'elif [ "$RUNTIME_MODE" = "wan" ]; then',
                    (
                        f"{binary} -A {chain} "
                        f"-i {policy.lan_interface} "
                        f"-o {policy.wan_interface} -j ACCEPT"
                    ),
                    "else",
                ]
            )

        if policy.allow_lan_to_vpn:
            lines.append(
                f"    {binary} -A {chain} "
                f"-i {policy.lan_interface} "
                f"-o {policy.vpn_interface} "
                "-j ACCEPT",
            )

            if binary == "iptables":
                lines.append(
                    f"    {binary} -A {chain} "
                    f"-i {policy.lan_interface} "
                    f"-o {policy.wan_interface} "
                    f"-m mark --mark {self.DIRECT_MARK} "
                    "-j ACCEPT",
                )

        if not policy.allow_lan_to_wan:
            lines.append(
                f"    {binary} -A {chain} "
                f"-i {policy.lan_interface} "
                f"-o {policy.wan_interface} "
                "-j DROP",
            )

        if binary == "iptables":
            lines.append("fi")

        if policy.allow_lan_to_wan_ipv6 and binary == "ip6tables":
            lines.append(
                f"{binary} -A {chain} "
                f"-i {policy.lan_interface} "
                f"-o {policy.wan_interface} "
                "-j ACCEPT",
            )

        if binary == "ip6tables":
            lines.append("fi")

        lines.extend(
            [
                f"{binary} -A {chain} -j RETURN",
                (
                    f"while {binary} -D {self.FORWARD_RULE_CHAIN} "
                    f"-j {chain} 2>/dev/null; do :; done"
                ),
                # The update guard is first. Keep an existing mode guard
                # ahead of policy ACCEPT rules when the update guard is removed.
                f'FORWARD_RULES="$({binary} -S {forward_chain})"',
                "POLICY_POSITION=2",
                f"""if printf '%s\\n' "$FORWARD_RULES" | grep -F -x -q -e "{mode_jump}" -e "-A {forward_chain} -g {mode_guard}"; then""",
                f'    if [ "$({binary} -S {forward_chain} 2 2>/dev/null || true)" != "{mode_jump}" ]; then',
                f"        {binary} -I {forward_chain} 2 -j {mode_guard}",
                "    fi",
                "    POLICY_POSITION=3",
                "fi",
                f'{binary} -I {forward_chain} "$POLICY_POSITION" -j {chain}',
            ],
        )

        return lines

    def _render_direct_nat(
        self,
        *,
        policy: VpnTrafficPolicy,
    ) -> list[str]:
        binary = "iptables"
        table = "nat"
        postrouting_chain = "POSTROUTING"

        return [
            (f"{binary} -t {table} -N {self.IPV4_NAT_CHAIN} 2>/dev/null || true"),
            f"{binary} -t {table} -F {self.IPV4_NAT_CHAIN}",
            (
                f"{binary} -t {table} -A {self.IPV4_NAT_CHAIN} "
                f"-o {policy.wan_interface} "
                f"-m mark --mark {self.DIRECT_MARK} "
                "-j MASQUERADE"
            ),
            (f"{binary} -t {table} -A {self.IPV4_NAT_CHAIN} -j RETURN"),
            (
                f"while {binary} -t {table} -D {postrouting_chain} "
                f"-j {self.IPV4_NAT_CHAIN} 2>/dev/null; do :; done"
            ),
            (f"{binary} -t {table} -I {postrouting_chain} 1 -j {self.IPV4_NAT_CHAIN}"),
        ]
