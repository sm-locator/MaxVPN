#!/usr/bin/env bash
# WSL/Linux operator wrapper. Nothing is installed on the router.
set -Eeuo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
usage() {
  cat <<'USAGE'
Usage:
  MAXVPN_ROUTER=root@192.168.8.1 ./scripts/brume3_pr6/run.sh preflight
  MAXVPN_ROUTER=root@192.168.8.1 ./scripts/brume3_pr6/run.sh backup
  MAXVPN_ROUTER=root@192.168.8.1 ./scripts/brume3_pr6/run.sh verify BACKUP_ID

Restore is intentionally disabled without a deployment receipt and explicit
operator confirmation:
  MAXVPN_ROUTER=root@192.168.8.1 ./scripts/brume3_pr6/run.sh restore BACKUP_ID RESTORE-BACKUP_ID

No deploy/install/restart operation is implemented here.
Do not paste private backup contents into chat or GitHub.
USAGE
}
[[ $# -gt 0 ]] || { usage; exit 2; }
ACTION="$1"; shift
case "$ACTION" in
  preflight|backup) [[ $# -eq 0 ]] || die "no arguments allowed" ;;
  verify)
    [[ $# -eq 1 ]] || die "verify requires BACKUP_ID"
    [[ "$1" =~ ^pr6-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] || die "invalid BACKUP_ID"
    ;;
  restore)
    [[ $# -eq 2 ]] || die "restore requires BACKUP_ID and explicit confirmation"
    [[ "$1" =~ ^pr6-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$ ]] || die "invalid BACKUP_ID"
    [[ "$2" == "RESTORE-$1" ]] || die "wrong restore confirmation"
    ;;
  -h|--help) usage; exit 0 ;;
  *) die "unsupported action; deploy is not available" ;;
esac

: "${MAXVPN_ROUTER:?Set MAXVPN_ROUTER=root@192.168.8.1 explicitly}"
[[ "$MAXVPN_ROUTER" =~ ^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.:-]+$ ]] ||
  die "MAXVPN_ROUTER must be user@hostname or user@IP"
[[ "$MAXVPN_ROUTER" == root@* ]] || die "Brume3 operations require root SSH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/router_snapshot.py"
[[ -f "$SOURCE" ]] || die "router_snapshot.py is missing"
command -v ssh >/dev/null 2>&1 || die "ssh is missing"
command -v python3 >/dev/null 2>&1 || die "python3 is missing"
python3 -m py_compile "$SOURCE"

echo "TARGET=$MAXVPN_ROUTER"
echo "ACTION=$ACTION"
echo "LIVE_MUTATION=NO_DEPLOY_NO_SERVICE_RESTART"
# Action and backup identifiers have been strictly whitelisted above.
# Only source code is sent over SSH stdin; no profile JSON is transmitted.
ssh -T -o StrictHostKeyChecking=yes \
  "$MAXVPN_ROUTER" "/usr/bin/python3 - $ACTION $*" < "$SOURCE"
