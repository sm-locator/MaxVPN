#!/usr/bin/env bash
# Install only the Brume 3 Smart Routing recovery server and WAN hotplug hook.
# This script intentionally does not restart the Appliance or invoke its CLI.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SOURCE="$SCRIPT_DIR/appliance/maxvpn/server.py"
HOTPLUG_SOURCE="$SCRIPT_DIR/appliance/maxvpn/hotplug.d/iface/99-maxvpn-restore-routing"

usage() {
  cat <<'USAGE'
Usage:
  MAXVPN_ROUTER=root@BRUME3 ./deploy_maxvpn_brume3_routing_restore_only.sh

Installs only appliance/maxvpn/server.py and
appliance/maxvpn/hotplug.d/iface/99-maxvpn-restore-routing.

The script creates and verifies a complete backup before changing either file,
and does not restart maxvpn-appliance. A restart is a separate operation.
USAGE
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required local command is unavailable: $1"
}

sha256_of() {
  sha256sum "$1" | awk '{print $1}'
}

check_python_syntax() {
  python3 - "$1" <<'PY'
import sys

path = sys.argv[1]
with open(path, "rb") as source:
    compile(source.read(), path, "exec")
PY
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
[[ $# -eq 0 ]] || { usage >&2; exit 2; }

: "${MAXVPN_ROUTER:?ERROR: set MAXVPN_ROUTER explicitly (for example root@BRUME3).}"

for command in ssh scp sha256sum python3 sh mktemp; do
  require_command "$command"
done

[[ -f "$SERVER_SOURCE" ]] || die "source server.py is missing: $SERVER_SOURCE"
[[ -f "$HOTPLUG_SOURCE" ]] || die "source hotplug file is missing: $HOTPLUG_SOURCE"
[[ -x "$HOTPLUG_SOURCE" ]] || die "source hotplug file must be executable: $HOTPLUG_SOURCE"

PAYLOAD_DIR="$(mktemp -d "${TMPDIR:-/tmp}/maxvpn-brume3-routing-restore.XXXXXX")"
STAMP="$(date -u +%Y%m%d-%H%M%S)-$$"
STAGE="/tmp/maxvpn-brume3-routing-restore-${STAMP}"
REMOTE_STAGE_CREATED=0
cleanup_local() {
  local rc=$?
  trap - EXIT HUP INT TERM
  if [[ "$REMOTE_STAGE_CREATED" -eq 1 ]]; then
    # STAGE has a fixed prefix and locally generated timestamp/PID suffix.
    ssh "$MAXVPN_ROUTER" "rm -rf -- '$STAGE'" >/dev/null 2>&1 ||
      printf 'WARNING: could not remove remote staging directory: %s\n' "$STAGE" >&2
  fi
  rm -rf "$PAYLOAD_DIR"
  exit "$rc"
}
trap cleanup_local EXIT HUP INT TERM

# Copy into a private local payload first, so the hashes cover exactly the two
# bytestrings later transmitted to the router and no source-tree pycache is made.
cp "$SERVER_SOURCE" "$PAYLOAD_DIR/server.py"
chmod 0644 "$PAYLOAD_DIR/server.py"
cp "$HOTPLUG_SOURCE" "$PAYLOAD_DIR/99-maxvpn-restore-routing"
chmod 0755 "$PAYLOAD_DIR/99-maxvpn-restore-routing"
check_python_syntax "$PAYLOAD_DIR/server.py"
sh -n "$PAYLOAD_DIR/99-maxvpn-restore-routing"

SERVER_SHA256="$(sha256_of "$PAYLOAD_DIR/server.py")"
HOTPLUG_SHA256="$(sha256_of "$PAYLOAD_DIR/99-maxvpn-restore-routing")"

printf 'Target: %s\n' "$MAXVPN_ROUTER"
printf 'Local server.py SHA-256: %s\n' "$SERVER_SHA256"
printf 'Local hotplug SHA-256: %s\n' "$HOTPLUG_SHA256"
printf 'Creating private remote staging directory...\n'
ssh "$MAXVPN_ROUTER" "umask 077 && mkdir '$STAGE'"
REMOTE_STAGE_CREATED=1

# These are intentionally the only files transferred by this scenario.
scp -O \
  "$PAYLOAD_DIR/server.py" \
  "$PAYLOAD_DIR/99-maxvpn-restore-routing" \
  "$MAXVPN_ROUTER:$STAGE/"

printf 'Verifying, backing up, and atomically installing the two files...\n'
ssh "$MAXVPN_ROUTER" "sh -s -- '$STAMP' '$SERVER_SHA256' '$HOTPLUG_SHA256'" <<'REMOTE'
set -eu
umask 077

STAMP="$1"
EXPECTED_SERVER_SHA256="$2"
EXPECTED_HOTPLUG_SHA256="$3"
STAGE="/tmp/maxvpn-brume3-routing-restore-${STAMP}"
APP_DIR="/opt/maxvpn-appliance"
SERVER_TARGET="$APP_DIR/server.py"
HOTPLUG_DIR="/etc/hotplug.d/iface"
HOTPLUG_TARGET="$HOTPLUG_DIR/99-maxvpn-restore-routing"
BACKUP_PARENT="$APP_DIR/backups"
BACKUP="$BACKUP_PARENT/brume3-routing-restore-${STAMP}"
BACKUP_WORK="$BACKUP_PARENT/.brume3-routing-restore-${STAMP}.incomplete-$$"
SERVER_TMP="$APP_DIR/.server.py.brume3-routing-restore-${STAMP}.new"
HOTPLUG_TMP="$HOTPLUG_DIR/.99-maxvpn-restore-routing.brume3-routing-restore-${STAMP}.new"
BACKUP_READY=0
BACKUP_WORK_CREATED=0
LIVE_MUTATION_STARTED=0

die() {
  echo "ERROR: $*" >&2
  exit 1
}

sha256_of() {
  sha256sum "$1" | awk '{print $1}'
}

assert_sha256() {
  actual="$(sha256_of "$1")"
  [ "$actual" = "$2" ] || die "SHA-256 mismatch for $1 (got $actual, expected $2)"
}

mode_of() {
  /usr/bin/python3 -c 'import os, sys; print(format(os.stat(sys.argv[1]).st_mode & 0o777, "o"))' "$1"
}

regular_file() {
  [ -f "$1" ] && [ ! -L "$1" ]
}

backup_error() {
  echo "ERROR: backup is incomplete or corrupt: $1" >&2
  return 1
}

# Require exactly two manifest entries and reject links before any live rename.
backup_is_valid() {
  b="$1"
  [ -d "$b" ] && [ ! -L "$b" ] || backup_error "backup directory is missing or a symlink" || return 1
  regular_file "$b/server.py" || backup_error "server.py is missing or a symlink" || return 1
  regular_file "$b/SHA256SUMS" || backup_error "SHA256SUMS is missing or a symlink" || return 1
  hp="$b/99-maxvpn-restore-routing"
  absent="$b/99-maxvpn-restore-routing.absent"
  if [ -e "$hp" ] || [ -L "$hp" ]; then
    regular_file "$hp" || backup_error "hotplug backup is not a regular file" || return 1
    [ ! -e "$absent" ] && [ ! -L "$absent" ] || backup_error "both hotplug states exist" || return 1
    hp_name=99-maxvpn-restore-routing
  else
    regular_file "$absent" || backup_error "hotplug backup or absent marker is missing" || return 1
    hp_name=99-maxvpn-restore-routing.absent
  fi
  [ "$(wc -l < "$b/SHA256SUMS")" -eq 2 ] || backup_error "SHA256SUMS must have two entries" || return 1
  server_sha="$(sha256_of "$b/server.py")"
  hotplug_sha="$(sha256_of "$b/$hp_name")"
  grep -Fqx "$server_sha  server.py" "$b/SHA256SUMS" || backup_error "server checksum is absent" || return 1
  grep -Fqx "$hotplug_sha  $hp_name" "$b/SHA256SUMS" || backup_error "hotplug checksum is absent" || return 1
  (cd "$b" && sha256sum -c SHA256SUMS >/dev/null 2>&1) || backup_error "checksum verification failed" || return 1
}

check_python_syntax() {
  /usr/bin/python3 - "$1" <<'PY'
import sys

path = sys.argv[1]
with open(path, "rb") as source:
    compile(source.read(), path, "exec")
PY
}

on_exit() {
  rc=$?
  trap - 0
  rm -f "$SERVER_TMP" "$HOTPLUG_TMP"
  if [ "$rc" -ne 0 ] && [ "$BACKUP_READY" -eq 1 ] && [ "$LIVE_MUTATION_STARTED" -eq 1 ]; then
    echo "Installation stopped. The live files may be mixed; do not restart the Appliance." >&2
    echo "Backup retained at: $BACKUP" >&2
    echo "To explicitly roll back, run:" >&2
    echo "  MAXVPN_ROUTER=<target> MAXVPN_BACKUP_STAMP=$STAMP ./rollback_maxvpn_brume3_routing_restore_only.sh" >&2
  fi
  [ "$BACKUP_WORK_CREATED" -eq 0 ] || rm -rf "$BACKUP_WORK"
  rm -rf "$STAGE"
  exit "$rc"
}
trap on_exit 0

for command in sha256sum awk grep wc cp mv rm mkdir chmod; do
  command -v "$command" >/dev/null 2>&1 || die "$command is required on the router"
done
[ -x /usr/bin/python3 ] || die "/usr/bin/python3 is required on the router"
[ -d "$APP_DIR" ] && [ ! -L "$APP_DIR" ] || die "application directory is missing or is a symlink"
[ -d "$HOTPLUG_DIR" ] && [ ! -L "$HOTPLUG_DIR" ] || die "hotplug directory is missing or is a symlink"
regular_file "$SERVER_TARGET" || die "live server.py is missing or is a symlink"
[ ! -L "$HOTPLUG_TARGET" ] || die "live hotplug target is a symlink (including a dangling symlink)"
if [ -e "$HOTPLUG_TARGET" ]; then regular_file "$HOTPLUG_TARGET" || die "live hotplug target is not a regular file"; fi
regular_file "$STAGE/server.py" || die "staged server.py is missing or is a symlink"
regular_file "$STAGE/99-maxvpn-restore-routing" || die "staged hotplug file is missing or is a symlink"
[ ! -e "$BACKUP" ] && [ ! -L "$BACKUP" ] || die "backup directory already exists (possibly incomplete): $BACKUP"

assert_sha256 "$STAGE/server.py" "$EXPECTED_SERVER_SHA256"
assert_sha256 "$STAGE/99-maxvpn-restore-routing" "$EXPECTED_HOTPLUG_SHA256"
check_python_syntax "$STAGE/server.py"
sh -n "$STAGE/99-maxvpn-restore-routing"

mkdir -p "$BACKUP_PARENT"
[ -d "$BACKUP_PARENT" ] && [ ! -L "$BACKUP_PARENT" ] || die "backup parent is not a real directory"
mkdir "$BACKUP_WORK" || die "could not create private incomplete backup directory"
BACKUP_WORK_CREATED=1
cp -p "$SERVER_TARGET" "$BACKUP_WORK/server.py"
if [ -e "$HOTPLUG_TARGET" ]; then
  cp -p "$HOTPLUG_TARGET" "$BACKUP_WORK/99-maxvpn-restore-routing"
else
  printf 'hotplug target was absent before installation\n' > "$BACKUP_WORK/99-maxvpn-restore-routing.absent"
fi
(cd "$BACKUP_WORK" && {
  sha256sum server.py > SHA256SUMS
  if [ -f 99-maxvpn-restore-routing ]; then sha256sum 99-maxvpn-restore-routing >> SHA256SUMS
  else sha256sum 99-maxvpn-restore-routing.absent >> SHA256SUMS; fi
})
backup_is_valid "$BACKUP_WORK" || die "refusing to use an invalid backup"
mv "$BACKUP_WORK" "$BACKUP"
BACKUP_WORK_CREATED=0
BACKUP_READY=1

# Both temporary files are prepared and checked on their destination filesystems
# before either live name is replaced. mv is an atomic rename on each filesystem.
rm -f "$SERVER_TMP" "$HOTPLUG_TMP"
cp "$STAGE/server.py" "$SERVER_TMP"
chmod 0644 "$SERVER_TMP"
cp "$STAGE/99-maxvpn-restore-routing" "$HOTPLUG_TMP"
chmod 0755 "$HOTPLUG_TMP"
assert_sha256 "$SERVER_TMP" "$EXPECTED_SERVER_SHA256"
assert_sha256 "$HOTPLUG_TMP" "$EXPECTED_HOTPLUG_SHA256"
check_python_syntax "$SERVER_TMP"
sh -n "$HOTPLUG_TMP"
[ "$(mode_of "$SERVER_TMP")" = "644" ] || die "temporary server.py mode is not 0644"
[ "$(mode_of "$HOTPLUG_TMP")" = "755" ] || die "temporary hotplug mode is not 0755"

LIVE_MUTATION_STARTED=1
mv -f "$SERVER_TMP" "$SERVER_TARGET"
mv -f "$HOTPLUG_TMP" "$HOTPLUG_TARGET"

assert_sha256 "$SERVER_TARGET" "$EXPECTED_SERVER_SHA256"
assert_sha256 "$HOTPLUG_TARGET" "$EXPECTED_HOTPLUG_SHA256"
check_python_syntax "$SERVER_TARGET"
sh -n "$HOTPLUG_TARGET"
[ "$(mode_of "$SERVER_TARGET")" = "644" ] || die "installed server.py mode is not 0644"
[ "$(mode_of "$HOTPLUG_TARGET")" = "755" ] || die "installed hotplug mode is not 0755"
[ -x "$HOTPLUG_TARGET" ] || die "installed hotplug file is not executable"

rm -rf "$STAGE"
trap - 0

echo "SUCCESS: only server.py and the WAN hotplug hook were installed."
echo "Backup: $BACKUP"
echo "No Appliance restart was performed. Restarting it requires separate confirmation."
REMOTE
REMOTE_STAGE_CREATED=0
