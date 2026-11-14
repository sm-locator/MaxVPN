#!/usr/bin/env bash
# Restore the two files saved by deploy_maxvpn_brume3_routing_restore_only.sh.
# This script never restarts the Appliance or invokes its CLI.
set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  MAXVPN_ROUTER=root@BRUME3 MAXVPN_BACKUP_STAMP=YYYYMMDD-HHMMSS-PID \
    ./rollback_maxvpn_brume3_routing_restore_only.sh

Restores server.py and the WAN hotplug hook from a verified deployment backup.
If the backup records that the hook was absent, the installed hook is removed.
No Appliance restart is performed.
USAGE
}
die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
need() { command -v "$1" >/dev/null 2>&1 || die "required local command is unavailable: $1"; }
valid_stamp() { [[ "$1" =~ ^[0-9]{8}-[0-9]{6}-[0-9]+$ ]]; }
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then usage; exit 0; fi
[[ $# -eq 0 ]] || { usage >&2; exit 2; }
: "${MAXVPN_ROUTER:?ERROR: set MAXVPN_ROUTER explicitly (for example root@BRUME3).}"
: "${MAXVPN_BACKUP_STAMP:?ERROR: set MAXVPN_BACKUP_STAMP from the deployment output.}"
valid_stamp "$MAXVPN_BACKUP_STAMP" || die "MAXVPN_BACKUP_STAMP must be YYYYMMDD-HHMMSS-PID"
need ssh

printf 'Target: %s\nBackup stamp: %s\n' "$MAXVPN_ROUTER" "$MAXVPN_BACKUP_STAMP"
printf 'Verifying the complete backup before restoring either live file...\n'
ssh "$MAXVPN_ROUTER" "sh -s -- '$MAXVPN_BACKUP_STAMP'" <<'REMOTE'
set -eu
umask 077
STAMP="$1"
APP_DIR="/opt/maxvpn-appliance"
SERVER_TARGET="$APP_DIR/server.py"
HOTPLUG_DIR="/etc/hotplug.d/iface"
HOTPLUG_TARGET="$HOTPLUG_DIR/99-maxvpn-restore-routing"
BACKUP="$APP_DIR/backups/brume3-routing-restore-${STAMP}"
SERVER_TMP="$APP_DIR/.server.py.brume3-routing-restore-${STAMP}.rollback-$$"
HOTPLUG_TMP="$HOTPLUG_DIR/.99-maxvpn-restore-routing.brume3-routing-restore-${STAMP}.rollback-$$"

die() { echo "ERROR: $*" >&2; exit 1; }
sha() { sha256sum "$1" | awk '{print $1}'; }
metadata() {
  /usr/bin/python3 - "$1" <<'PY'
import os
import stat
import sys

info = os.stat(sys.argv[1], follow_symlinks=False)
print(f"{info.st_uid}:{info.st_gid}:{stat.S_IMODE(info.st_mode):o}")
PY
}
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
syntax_python() {
  /usr/bin/python3 - "$1" <<'PY'
import sys
with open(sys.argv[1], "rb") as source:
    compile(source.read(), sys.argv[1], "exec")
PY
}
backup_error() { echo "ERROR: backup is incomplete or corrupt: $1" >&2; return 1; }
backup_is_valid() {
  b="$1"
  [ -d "$b" ] && [ ! -L "$b" ] || backup_error "backup directory is missing or a symlink" || return 1
  regular "$b/server.py" || backup_error "server.py is missing or a symlink" || return 1
  regular "$b/SHA256SUMS" || backup_error "SHA256SUMS is missing or a symlink" || return 1
  hp="$b/99-maxvpn-restore-routing"; absent="$b/99-maxvpn-restore-routing.absent"
  if [ -e "$hp" ] || [ -L "$hp" ]; then
    regular "$hp" || backup_error "hotplug backup is not a regular file" || return 1
    [ ! -e "$absent" ] && [ ! -L "$absent" ] || backup_error "both hotplug states exist" || return 1
    hp_name=99-maxvpn-restore-routing
  else
    regular "$absent" || backup_error "hotplug backup or absent marker is missing" || return 1
    hp_name=99-maxvpn-restore-routing.absent
  fi
  [ "$(wc -l < "$b/SHA256SUMS")" -eq 2 ] || backup_error "SHA256SUMS must have two entries" || return 1
  server_sha="$(sha "$b/server.py")"; hotplug_sha="$(sha "$b/$hp_name")"
  grep -Fqx "$server_sha  server.py" "$b/SHA256SUMS" || backup_error "server checksum is absent" || return 1
  grep -Fqx "$hotplug_sha  $hp_name" "$b/SHA256SUMS" || backup_error "hotplug checksum is absent" || return 1
  (cd "$b" && sha256sum -c SHA256SUMS >/dev/null 2>&1) || backup_error "checksum verification failed" || return 1
}
copy_preserving() {
  cp -p "$1" "$2" || return 1
  [ "$(metadata "$1")" = "$(metadata "$2")" ] ||
    echo "WARNING: metadata could not be preserved exactly for $2" >&2
}
cleanup() { rc=$?; trap - 0; rm -f "$SERVER_TMP" "$HOTPLUG_TMP"; exit "$rc"; }
trap cleanup 0

case "$STAMP" in
  [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]-[0-9]*) ;;
  *) die "invalid backup stamp" ;;
esac
for c in sha256sum awk grep wc cp mv rm; do command -v "$c" >/dev/null 2>&1 || die "$c is required on the router"; done
[ -x /usr/bin/python3 ] || die "/usr/bin/python3 is required on the router"
[ -d "$APP_DIR" ] && [ ! -L "$APP_DIR" ] || die "application directory is missing or is a symlink"
[ -d "$HOTPLUG_DIR" ] && [ ! -L "$HOTPLUG_DIR" ] || die "hotplug directory is missing or is a symlink"

# No live name or temporary file is touched before this complete validation.
backup_is_valid "$BACKUP" || die "refusing to restore from an invalid backup"
if [ -f "$BACKUP/99-maxvpn-restore-routing" ]; then kind=file; else kind=absent; fi

# Do not replace a directory. A symlink is replaced/removed as a name, not
# followed, so a dangling installed hotplug symlink is safely repaired.
[ ! -d "$SERVER_TARGET" ] || [ -L "$SERVER_TARGET" ] || die "live server.py is a directory"
[ ! -d "$HOTPLUG_TARGET" ] || [ -L "$HOTPLUG_TARGET" ] || die "live hotplug target is a directory"
rm -f "$SERVER_TMP" "$HOTPLUG_TMP"
copy_preserving "$BACKUP/server.py" "$SERVER_TMP" || die "could not prepare temporary server.py"
[ "$(sha "$SERVER_TMP")" = "$(sha "$BACKUP/server.py")" ] || die "temporary server.py checksum mismatch"
syntax_python "$SERVER_TMP"
if [ "$kind" = file ]; then
  copy_preserving "$BACKUP/99-maxvpn-restore-routing" "$HOTPLUG_TMP" || die "could not prepare temporary hotplug"
  [ "$(sha "$HOTPLUG_TMP")" = "$(sha "$BACKUP/99-maxvpn-restore-routing")" ] || die "temporary hotplug checksum mismatch"
  sh -n "$HOTPLUG_TMP"
fi

# These are atomic renames on their individual destination filesystems.
mv -f "$SERVER_TMP" "$SERVER_TARGET"
if [ "$kind" = file ]; then mv -f "$HOTPLUG_TMP" "$HOTPLUG_TARGET"; else rm -f "$HOTPLUG_TARGET"; fi
[ "$(sha "$SERVER_TARGET")" = "$(sha "$BACKUP/server.py")" ] || die "restored server.py checksum mismatch"
syntax_python "$SERVER_TARGET"
if [ "$(metadata "$SERVER_TARGET")" != "$(metadata "$BACKUP/server.py")" ]; then
  echo "WARNING: server.py metadata could not be preserved exactly" >&2
fi
if [ "$kind" = file ]; then
  [ "$(sha "$HOTPLUG_TARGET")" = "$(sha "$BACKUP/99-maxvpn-restore-routing")" ] || die "restored hotplug checksum mismatch"
  sh -n "$HOTPLUG_TARGET"
  if [ "$(metadata "$HOTPLUG_TARGET")" != "$(metadata "$BACKUP/99-maxvpn-restore-routing")" ]; then
    echo "WARNING: hotplug metadata could not be preserved exactly" >&2
  fi
else
  [ ! -e "$HOTPLUG_TARGET" ] && [ ! -L "$HOTPLUG_TARGET" ] || die "hotplug was recorded as absent but could not be removed"
fi
trap - 0
echo "SUCCESS: server.py and the WAN hotplug state were restored from $BACKUP."
echo "No Appliance restart was performed. Restarting it requires separate confirmation."
REMOTE
