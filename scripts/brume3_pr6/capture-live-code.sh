#!/usr/bin/env bash
# Copy only code/scripts into a private WSL folder for an exact three-way review.
# Never collect the VLESS profile store, sing-box config or subscription URLs.
set -Eeuo pipefail

die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
: "${MAXVPN_ROUTER:?Set MAXVPN_ROUTER=root@192.168.8.1}"
[[ "$MAXVPN_ROUTER" =~ ^root@[a-zA-Z0-9_.:-]+$ ]] || die "unsafe router address"
command -v ssh >/dev/null 2>&1 || die "ssh is required"
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required"
PRIVATE_DIR="${MAXVPN_PRIVATE_DIR:-$HOME/.local/share/maxvpn-pr6-private}"
[[ ! -L "$PRIVATE_DIR" ]] || die "private folder is symlink"
mkdir -p -m 0700 "$PRIVATE_DIR"
chmod 0700 "$PRIVATE_DIR"
SNAPSHOT="$PRIVATE_DIR/live-$(date -u +%Y%m%dT%H%M%SZ)-$$"
(umask 077; mkdir "$SNAPSHOT") || die "cannot create private snapshot"
trap 'test -z "${tmp:-}" || rm -f "$tmp"' EXIT

# Do not include /etc/maxvpn/vless-profiles.json or sing-box-vless.json here.
PATHS=(
  /opt/maxvpn-appliance/server.py
  /opt/maxvpn-appliance/vless_control.py
  /opt/maxvpn-appliance/vless_subscription.py
  /www/maxvpn/index.html
  /usr/bin/maxvpn-vless-watchdog
  /usr/bin/vpn-lan-on
  /usr/bin/vpn-lan-off
  /usr/bin/vpn-lan-vless-on
  /etc/init.d/maxvpn-sing-box
  /etc/init.d/maxvpn-vless-watchdog
  /etc/maxvpn/firewall.user
  /etc/hotplug.d/iface/99-lan-vpn
)
for remote in "${PATHS[@]}"; do
  local_name="${remote#/}"
  local_name="${local_name//\//__}"
  target="$SNAPSHOT/$local_name"
  tmp="$(mktemp "$SNAPSHOT/.capture.XXXXXX")" || die "mktemp failed"
  chmod 0600 "$tmp"
  # Every remote filename above is a literal trusted path. Read only.
  if ! ssh -T -o StrictHostKeyChecking=yes "$MAXVPN_ROUTER" \
     "[ -f '$remote' ] && [ ! -L '$remote' ] && cat '$remote'" > "$tmp"; then
    die "failed to read remote code: $remote"
  fi
  mv "$tmp" "$target"
  tmp=""
done

# Refuse to use a mismatched historical production source.
verify_one() {
  local path="$1" expected="$2" filename got
  filename="${path#/}"
  filename="${filename//\//__}"
  got="$(sha256sum "$SNAPSHOT/$filename" | awk '{print $1}')"
  [[ "$got" == "$expected" ]] || die "Baseline SHA mismatch: $path"
}
verify_one /opt/maxvpn-appliance/server.py \
  3b3919434698d31244cec87247d10eafacf31eba1f0a8fa3fe539d0cf07c53f5
verify_one /opt/maxvpn-appliance/vless_control.py \
  ae97cedaa795f06af99e898b92bf80cb06f1c40558213b353df949d5ec772189
verify_one /opt/maxvpn-appliance/vless_subscription.py \
  03d1f623034bc02861f593866fb827d41146c5e343f7f65e5a4070fb4ceb5c64
verify_one /www/maxvpn/index.html \
  c50d460900af781e5c32f740eab2484da1defe10eaf95ab341231ef906bc3649

( cd "$SNAPSHOT" && sha256sum * > SHA256SUMS )
chmod 0600 "$SNAPSHOT/SHA256SUMS"
echo "PRIVATE_SOURCE_CAPTURE=OK"
echo "PRIVATE_LOCATION=$SNAPSHOT"
echo "NO_PROFILE_JSON_COLLECTED=YES"
echo "NO_ROUTER_FILE_MODIFIED=YES"
echo "DO_NOT_GIT_ADD_OR_UPLOAD_PRIVATE_SNAPSHOT=YES"
