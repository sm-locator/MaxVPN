# Brume 3 / PR #6 — gated migration toolkit (2026-11-21)

This is a **pre-deployment** package, not a production installer.
It runs from Linux/WSL2 over SSH on GL.iNet GL-MT5000 CN firmware.

## Safety model

The running router has privately adapted appliance code. The complete
production-specific source diff is NOT in GitHub; replacing server.py,
vless_control.py or index.html wholesale from PR #6 is unsafe.

**No deploy, install, apply, or restart action is implemented.**

| Action | Router changes |
|---|---|
| preflight | read-only |
| capture-live-code.sh | read-only; local private source copies |
| backup | creates a private backup only; no services restarted |
| verify BACKUP_ID | read-only verification of backup |
| restore BACKUP_ID RESTORE-BACKUP_ID | gated: requires future approved deployment receipt; refuses by default |

Backups include VLESS profile and sing-box JSON credentials and remain
in mode-0700 private directories on the router, with mode-0600 files.
DO NOT upload backup files, private source, JSON credentials or provider URLs.

## Separate WSL2 worktree (no changes to existing checkout)

~~~bash
cd ~/Projects/MaxVPN
git fetch https://github.com/sm-locator/MaxVPN.git feature/vless-bulk-delete-outage
git worktree add --detach ~/Projects/MaxVPN-pr6-gated FETCH_HEAD
cd ~/Projects/MaxVPN-pr6-gated
~~~

## Read-only preflight

~~~bash
export MAXVPN_ROUTER=root@192.168.8.1
bash scripts/brume3_pr6/run.sh preflight
~~~

SSH StrictHostKeyChecking=yes requires a previously trusted host key.
Preflight compares the four known production code hashes, runtime mode,
flock presence, IPv4/IPv6 hook, DIRECT and legacy printer route.

## Explicit private backup and verification (no VPN restart)

~~~bash
bash scripts/brume3_pr6/run.sh backup
# Save the BACKUP_ID=pr6-... shown in the output:
bash scripts/brume3_pr6/run.sh verify pr6-YYYYMMDDTHHMMSSZ-XXXXXXXX
~~~

Do not send backup contents to chat, email, GitHub or any third party.

## Capture production source to private WSL directory

~~~bash
MAXVPN_PRIVATE_DIR="$HOME/.local/share/maxvpn-pr6-private" \
  bash scripts/brume3_pr6/capture-live-code.sh
~~~

Copies 12 source/scripts without retrieving the VLESS profile store or
sing-box config. Validates four production hashes. Keep the directory
outside the repository, with mode 0700. DO NOT git add or upload it.
The private source is needed for an exact three-way merge.

## Candidate modules (not installable as-is)

- appliance/maxvpn/compat/brume3-watchdog-locked.sh: mode-aware
  shared flock around repair/service restart, process PID/tick marker.
- appliance/maxvpn/compat/brume3-vless-stop-guarded.sh: rejects sing-box
  stop while LAN uses VLESS, checks protected VPN or explicit WAN.
- appliance/maxvpn/vless_control.py: locks bulk deletion and stop,
  preserves rollback boundaries and refuses incompatible watchdog.

## Restore gate

router_snapshot.py has a restore implementation with SHA-256 validation,
exact confirmation text, and allowlisted file paths. It REQUIRES a
deployment-receipt.json containing post-deploy checksums. This package
deliberately DOES NOT create such a receipt because there is no approved
installer yet. Therefore restore is blocked on the current live device.

After a future approved deployment, a separate installer must write
the receipt. Restore will never automatically change runtime mode,
firewall, DNS, DIRECT, printer routing, profile JSON or service state.

## Deployment blockers

1. Generate a device-specific three-way merge from private live source
   and PR #6; do not replace the whole appliance from GitHub.
2. Isolated OpenWrt 21.02 and Python 3.9 testing of candidate files.
3. Confirm shared flock and running watchdog identity after a
   separately authorized restart.
4. Add a guarded installer with full SHA-256 checks and a deployment
   receipt, then verify coordinated rollback before use.
5. Request separate explicit authorization for actual deployment.

Never test bulk deletion on the production Brume 3.
See docs/deployments/brume3-vless-bulk-delete-20261121.md for baseline.
