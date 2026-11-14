#!/usr/bin/env bash
set -Eeuo pipefail

# Run a read-only IPv4 audit and archive both its full console output and a
# short Markdown index. This wrapper intentionally supports audit mode only;
# interactive capture remains a separate command so Ctrl+C never interrupts
# report finalization.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DIAGNOSTIC="$SCRIPT_DIR/maxvpn_smart_routing_ipv4_diagnostic.sh"

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/run_maxvpn_smart_routing_report.sh domain.example [domain.example ...]

Optional environment:
  MAXVPN_ROUTER=root@192.168.8.1
  MAXVPN_LAN_CLIENT_IP=192.168.8.X  actual IPv4 of a client on br-lan
  MAXVPN_REPORT_DIR=/path/to/report-directory

Runs the read-only audit mode and saves a timestamped .log and .md report.
USAGE
}

if (($# == 0)) || [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ ! -x "$DIAGNOSTIC" ]]; then
  echo "ERROR: diagnostic script not found or not executable: $DIAGNOSTIC" >&2
  exit 2
fi

REPORT_DIR="${MAXVPN_REPORT_DIR:-$ROOT/exports/diagnostics}"
mkdir -p "$REPORT_DIR"
STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG="$REPORT_DIR/maxvpn-smart-routing-ipv4-audit-$STAMP.log"
SUMMARY="$REPORT_DIR/maxvpn-smart-routing-ipv4-audit-$STAMP.md"
DOMAINS="$*"
STARTED_AT="$(date '+%Y-%m-%d %H:%M:%S %z')"
CLIENT_IP="${MAXVPN_LAN_CLIENT_IP:-not specified}"

printf 'Archiving audit output to: %s\n' "$LOG"
set +e
bash "$DIAGNOSTIC" audit "$@" 2>&1 | tee "$LOG"
DIAGNOSTIC_RC=${PIPESTATUS[0]}
set -e

PASS_COUNT="$(grep -c '^\[PASS\]' "$LOG" || true)"
WARN_COUNT="$(grep -c '^\[WARN\]' "$LOG" || true)"
FAIL_COUNT="$(grep -c '^\[FAIL\]' "$LOG" || true)"
INFO_COUNT="$(grep -c '^\[INFO\]' "$LOG" || true)"
if ((DIAGNOSTIC_RC == 0 && FAIL_COUNT == 0)); then
  RESULT="PASS"
else
  RESULT="FAIL"
fi

cat > "$SUMMARY" <<EOF
# MaxVPN Smart Routing IPv4 audit

- Time: $STARTED_AT
- Domains: $DOMAINS
- Router: ${MAXVPN_ROUTER:-root@192.168.8.1}
- Optional LAN client IPv4: $CLIENT_IP
- IPv6: N/A — ISP does not provide IPv6; IPv6 was not checked or changed.
- Result: **$RESULT**
- Diagnostic exit code: $DIAGNOSTIC_RC
- Counts in the output: PASS=$PASS_COUNT, WARN=$WARN_COUNT, FAIL=$FAIL_COUNT, INFO=$INFO_COUNT
- Full console transcript: $(basename "$LOG")

The diagnostic is read-only. It does not modify routes, ipsets, firewall rules,
VPN settings, or packet counters. The dynamic DIRECT counter is shared by
matching LAN traffic and is not specific to any one domain.
EOF

printf '\nReport saved:\n  %s\n  %s\n' "$LOG" "$SUMMARY"
exit "$DIAGNOSTIC_RC"
