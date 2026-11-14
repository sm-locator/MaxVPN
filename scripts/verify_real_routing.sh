#!/usr/bin/env bash
set -euo pipefail

# MaxVPN real-path regression test.
# Run from WSL on the Windows host that is connected to Brume 3.
# It verifies:
#   1) ordinary LAN traffic exits through WireGuard (table 100),
#   2) DIRECT traffic exits through WAN (table 200),
#   3) the external/public IPs are different,
#   4) the DIRECT mangle counter actually increases,
#   5) IPv4 policy rules are present exactly once.
#
# Usage:
#   ./scripts/verify_real_routing.sh [client-ip]
# Example:
#   ./scripts/verify_real_routing.sh 192.168.8.231

ROUTER="${ROUTER:-GL-MT5000}"
CLIENT_IP="${1:-${CLIENT_IP:-192.168.8.231}}"
TEST_HOST="${TEST_HOST:-}"
CURL_TIMEOUT="${CURL_TIMEOUT:-15}"
TEST_HOST_CANDIDATES=(api.ipify.org ipv4.icanhazip.com ifconfig.me)
SSH_TIMEOUT="${SSH_TIMEOUT:-10}"

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

info() {
    echo "[+] $*"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "command not found: $1"
}

require_command ssh
require_command powershell.exe
require_command tr
require_command awk
require_command grep
require_command sort

[[ "$CLIENT_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "invalid client IPv4: $CLIENT_IP"

for octet in ${CLIENT_IP//./ }; do
    (( octet <= 255 )) || fail "invalid client IPv4: $CLIENT_IP"
done

SSH_SOCKET="/tmp/maxvpn-verify-${BASHPID}"
SSH_OPTS=(
    -o "ConnectTimeout=${SSH_TIMEOUT}"
    -o ControlMaster=auto
    -o ControlPersist=2m
    -o "ControlPath=${SSH_SOCKET}"
)

ORIGINAL_DIRECT_STATE="unknown"
TEST_IP=""

restore_test_ip() {
    case "$ORIGINAL_DIRECT_STATE" in
        present)
            ssh_router "ipset add MAXVPN_DIRECT '${TEST_IP}' >/dev/null 2>&1 || true"
            ;;
        absent)
            ssh_router "ipset del MAXVPN_DIRECT '${TEST_IP}' >/dev/null 2>&1 || true"
            ;;
    esac
}

cleanup() {
    local rc=$?
    if [[ -n "$TEST_IP" && "$ORIGINAL_DIRECT_STATE" != "unknown" ]]; then
        restore_test_ip >/dev/null 2>&1 || true
    fi
    ssh "${SSH_OPTS[@]}" -O exit "root@${ROUTER}" >/dev/null 2>&1 || true
    rm -f "$SSH_SOCKET" >/dev/null 2>&1 || true
    exit "$rc"
}
trap cleanup EXIT

ssh_router() {
    ssh "${SSH_OPTS[@]}" "root@${ROUTER}" "$1"
}

# Create the SSH control connection once so a password, when required, is requested only once.
info "Connecting to ${ROUTER}"
ssh_router 'true' >/dev/null

# Pick a public-IP endpoint whose resolved address is not already in MAXVPN_DIRECT.
# This keeps the VPN leg clean and avoids temporarily removing a live Smart Routing entry.
CANDIDATE_LIST=("${TEST_HOST}")
if [[ -z "$TEST_HOST" ]]; then
    CANDIDATE_LIST=("${TEST_HOST_CANDIDATES[@]}")
fi

for candidate in "${CANDIDATE_LIST[@]}"; do
    [[ -n "$candidate" ]] || continue
    mapfile -t candidate_ips < <(
        ssh_router "nslookup '${candidate}' 2>/dev/null | awk '/Address [0-9]+: [0-9]+\\./ {print \$NF}' | sort -u"
    )
    for candidate_ip in "${candidate_ips[@]}"; do
        [[ "$candidate_ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || continue
        if ! ssh_router "ipset test MAXVPN_DIRECT '${candidate_ip}' >/dev/null 2>&1"; then
            TEST_HOST="$candidate"
            TEST_IP="$candidate_ip"
            break 2
        fi
    done
done

# Fallback: use api.ipify.org and restore its original membership if necessary.
if [[ -z "$TEST_HOST" || -z "$TEST_IP" ]]; then
    TEST_HOST="api.ipify.org"
    mapfile -t TEST_IPS < <(
        ssh_router "nslookup '${TEST_HOST}' 2>/dev/null | awk '/Address [0-9]+: [0-9]+\\./ {print \$NF}' | sort -u"
    )
    ((${#TEST_IPS[@]} > 0)) || fail "no IPv4 address found for ${TEST_HOST}"
    TEST_IP="${TEST_IPS[0]}"
fi

[[ "$TEST_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "invalid resolved IPv4: $TEST_IP"
info "Using ${TEST_HOST} -> ${TEST_IP}"

wan_ip="$(ssh_router "curl -4 -sS --fail --connect-timeout ${CURL_TIMEOUT} https://${TEST_HOST}" | tr -d '\r\n')"
[[ "$wan_ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "could not determine Brume WAN public IP: '${wan_ip}'"
info "Brume WAN public IP: ${wan_ip}"

ipset_state() {
    if ssh_router "ipset test MAXVPN_DIRECT '${TEST_IP}' >/dev/null 2>&1"; then
        echo present
    else
        echo absent
    fi
}

ORIGINAL_DIRECT_STATE="$(ipset_state)"
info "${TEST_IP} in MAXVPN_DIRECT before test: ${ORIGINAL_DIRECT_STATE}"

# For the VPN leg the test address must not be in DIRECT. The candidate selection normally
# guarantees this; fallback to a temporary removal only when every candidate is already DIRECT.
if [[ "$ORIGINAL_DIRECT_STATE" == present ]]; then
    info "Temporarily removing ${TEST_IP} from MAXVPN_DIRECT for the VPN leg"
    ssh_router "ipset del MAXVPN_DIRECT '${TEST_IP}'"
fi

# Verify the policy tables before generating traffic.
[[ "$(ipset_state)" == absent ]] || fail "${TEST_IP} is still in MAXVPN_DIRECT before the VPN leg"
normal_route="$(ssh_router "ip route get 1.1.1.1 from '${CLIENT_IP}' iif br-lan 2>/dev/null")"
[[ "$normal_route" == *"table 100"* ]] || fail "normal LAN lookup is not using table 100: ${normal_route}"
[[ "$normal_route" == *"dev WireGuard"* ]] || fail "normal LAN lookup is not using WireGuard: ${normal_route}"
info "Normal route: ${normal_route}"

echo "=== NORMAL VPN PUBLIC IP ==="
normal_ip="$({
    powershell.exe -NoProfile -NonInteractive -Command \
        "\$ErrorActionPreference='Stop'; & curl.exe -4 --silent --show-error --fail --connect-timeout ${CURL_TIMEOUT} --resolve '${TEST_HOST}:443:${TEST_IP}' 'https://${TEST_HOST}'; if (\$LASTEXITCODE -ne 0) { exit \$LASTEXITCODE }"
} | tr -d '\r\n')"

echo "${normal_ip}"
[[ "$normal_ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "VPN public IP is not an IPv4 address: '${normal_ip}'"
[[ "$normal_ip" != "$wan_ip" ]] || fail "VPN and WAN public IPs are identical: ${normal_ip}"
info "VPN public IP: ${normal_ip}"

# Put the same TEST_IP into DIRECT and verify the marked policy path.
info "Adding ${TEST_IP} to MAXVPN_DIRECT for the DIRECT leg"
ssh_router "ipset add MAXVPN_DIRECT '${TEST_IP}'"

[[ "$(ipset_state)" == present ]] || fail "${TEST_IP} was not added to MAXVPN_DIRECT"

direct_route="$(ssh_router "ip route get '${TEST_IP}' from '${CLIENT_IP}' iif br-lan mark 0x64 2>/dev/null")"
[[ "$direct_route" == *"table 200"* ]] || fail "DIRECT lookup is not using table 200: ${direct_route}"
[[ "$direct_route" == *"dev eth1"* ]] || fail "DIRECT lookup is not using WAN eth1: ${direct_route}"
info "DIRECT route: ${direct_route}"

before_count="$(ssh_router "iptables -t mangle -L PREROUTING -v -n | awk '\$0 ~ /match-set MAXVPN_DIRECT dst/ {print \$1; exit}'")"
[[ "$before_count" =~ ^[0-9]+$ ]] || fail "could not read MAXVPN_DIRECT mangle counter: '${before_count}'"
info "DIRECT mangle counter before traffic: ${before_count}"

echo "=== DIRECT WAN PUBLIC IP ==="
direct_ip="$({
    powershell.exe -NoProfile -NonInteractive -Command \
        "\$ErrorActionPreference='Stop'; & curl.exe -4 --silent --show-error --fail --connect-timeout ${CURL_TIMEOUT} --resolve '${TEST_HOST}:443:${TEST_IP}' 'https://${TEST_HOST}'; if (\$LASTEXITCODE -ne 0) { exit \$LASTEXITCODE }"
} | tr -d '\r\n')"

echo "${direct_ip}"
[[ "$direct_ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "DIRECT public IP is not an IPv4 address: '${direct_ip}'"
[[ "$direct_ip" == "$wan_ip" ]] || fail "DIRECT public IP ${direct_ip} does not match Brume WAN IP ${wan_ip}"
[[ "$direct_ip" != "$normal_ip" ]] || fail "DIRECT and VPN public IPs are identical: ${direct_ip}"

sleep 1
after_count="$(ssh_router "iptables -t mangle -L PREROUTING -v -n | awk '\$0 ~ /match-set MAXVPN_DIRECT dst/ {print \$1; exit}'")"
[[ "$after_count" =~ ^[0-9]+$ ]] || fail "could not read DIRECT mangle counter after traffic: '${after_count}'"

if (( after_count <= before_count )); then
    fail "DIRECT mangle counter did not increase (${before_count} -> ${after_count})"
fi
info "DIRECT mangle counter after traffic: ${after_count}"

# Exact rule-shape checks that catch the duplicate/legacy MARK regression.
rule_count="$(ssh_router "iptables -t mangle -S PREROUTING | grep -Ec -- '-m set --match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x64/0xff' || true")"
static_rule_count="$(ssh_router "iptables -t mangle -S PREROUTING | grep -Ec -- '-m set --match-set MAXVPN_DIRECT_STATIC dst -j MARK --set-xmark 0x64/0xff' || true")"
ip_rule_count="$(ssh_router "ip rule show | grep -Ec '^100:.*fwmark 0x64/0xff.*lookup 200$' || true")"
lan_rule_count="$(ssh_router "ip rule show | grep -Ec '^1000:.*iif br-lan.*lookup 100$' || true")"
table200_default_count="$(ssh_router "ip -4 route show table 200 | awk '\$1==\"default\" && \$0 ~ / dev eth1([[:space:]]|$)/ {count++} END {print count+0}'")"

[[ "$rule_count" == 1 ]] || fail "expected exactly one IPv4 DIRECT mangle rule, got ${rule_count}"
[[ "$static_rule_count" == 1 ]] || fail "expected exactly one IPv4 STATIC DIRECT mangle rule, got ${static_rule_count}"
[[ "$ip_rule_count" == 1 ]] || fail "expected exactly one fwmark priority-100 rule, got ${ip_rule_count}"
[[ "$lan_rule_count" == 1 ]] || fail "expected exactly one LAN priority-1000 rule, got ${lan_rule_count}"
[[ "$table200_default_count" == 1 ]] || fail "expected exactly one WAN default route in table 200, got ${table200_default_count}"

# Restore the exact original membership of the test address.
restore_test_ip

cat <<SUMMARY

=== MAXVPN REAL ROUTING REGRESSION: PASS ===
Client:       ${CLIENT_IP}
Test host:    ${TEST_HOST} -> ${TEST_IP}
VPN public IP:    ${normal_ip}
DIRECT public IP: ${direct_ip}
WAN public IP:    ${wan_ip}
Mangle DIRECT:    ${before_count} -> ${after_count}
IPv4 DIRECT rule: ${rule_count}
IPv4 STATIC rule:  ${static_rule_count}
fwmark rule:       ${ip_rule_count}
LAN rule:          ${lan_rule_count}
table 200 default: ${table200_default_count}

Normal LAN traffic -> table 100 / WireGuard
DIRECT LAN traffic -> mark 0x64 -> table 200 / WAN
=== END ===
SUMMARY
