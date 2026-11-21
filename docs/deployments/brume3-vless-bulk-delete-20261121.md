# GL-MT5000 CN: VLESS bulk-delete/availability rollout gate (2026-11-21)

## Evidence (read-only router inspection, 21 Nov 2026)

- OpenWrt 21.02-SNAPSHOT, kernel 5.4.281, Python 3.9.18, SQLite 3.40.0.
- Active route mode **vless**, sing-box and watchdog running/enabled.
- 15 saved VLESS profiles; WAN fallback explicitly enabled (**Kill Switch OFF**).
- IPv4 LAN policy table 100 defaults to `maxvpn0`; DIRECT mark `0x64/0xff` uses table 200 via `eth1`; 416 entries in `MAXVPN_DIRECT`.
- The legacy printer route to `192.168.31.137` and subnet `192.168.31.0/24` are present and must be preserved.
- IPv4 `forwarding_rule -> MAXVPN_LAN_FORWARD` and IPv6 `forwarding_rule -> MAXVPN_LAN6_FORWARD` are installed.
- `/usr/bin/flock` exists.
- `/usr/bin/vpn-lan-on`, `vpn-lan-off`, `vpn-lan-vless-on` and the original live watchdog do **not** take a routing flock.
- Production `server.py` uses `/opt/maxvpn-appliance/run/apply.lock`, while the original PR #6 deletion code used `/tmp/maxvpn-runtime.lock`; the branch now uses the shared `apply.lock`.
- `/usr/bin/vpn-lan-vless-stop` is **absent**. The stop API still references it; do not assume full source replacement is safe.

The live files are a device-specific partial merge, **not** copies of the current PR branch.
Baseline SHA256 hashes from the router:

| File | SHA256 |
| --- | --- |
| `/opt/maxvpn-appliance/server.py` | `3b3919434698d31244cec87247d10eafacf31eba1f0a8fa3fe539d0cf07c53f5` |
| `/opt/maxvpn-appliance/vless_control.py` | `ae97cedaa795f06af99e898b92bf80cb06f1c40558213b353df949d5ec772189` |
| `/opt/maxvpn-appliance/vless_subscription.py` | `03d1f623034bc02861f593866fb827d41146c5e343f7f65e5a4070fb4ceb5c64` |
| `/www/maxvpn/index.html` | `c50d460900af781e5c32f740eab2484da1defe10eaf95ab341231ef906bc3649` |

## Coordinated locking

1. Appliance `server.routing_lock()` owns `/opt/maxvpn-appliance/run/apply.lock` during Smart Routing mutations and restore.
2. `VlessControl.delete_all_profiles()` takes that **same** lock *before* changing the LAN mode, holds it through the empty-store commit, and holds it through any error rollback.
3. The reviewed candidate watchdog in `appliance/maxvpn/compat/brume3-watchdog-locked.sh` is based on the **actual installed** shell watchdog. It acquires the same lock **only** around:
   - VLESS policy repair helper;
   - sing-box service start/restart;
   - VLESS route repair following service recovery.
   Once the lock is obtained, the watchdog checks that runtime mode is still `vless`; if the LAN is already `wan`, the pending repair is skipped. It releases the fd lock on return.
4. Existing `vpn-lan-*` scripts are intentionally **not** rewritten here. They contain no internal flock: making them acquire the lock naively would deadlock when called by Python already holding the lock. Direct external invocations outside the appliance remain an operational concurrency risk and must not occur during maintenance.

## Rollout gate — no changes permitted until all conditions pass

- Ensure GitHub CI success on **the latest commit**, including watchdog shell syntax and lock contention tests.
- Produce a device-specific minimal patch by comparing live files against exact source SHA256; never overwrite existing router Smart Routing/firewall/DNS/printer configuration with repository defaults.
- Decide how the missing `vpn-lan-vless-stop` is handled, and test stop/recovery. Do not install a half-compatible stop API.
- Run isolated OpenWrt/busybox shell tests for `flock -x 9` and `flock -u 9`, including mode change while the watchdog is waiting. Linux CI alone does not establish identical GL-MT5000 behaviour.
- Create a private **complete** backup of the installed `server.py`, `vless_control.py`, `vless_subscription.py`, `index.html`, watchdog, their init scripts, `firewall.user`, route helpers, and VLESS JSON state/config before any replacement. Store with 0700 parent/0600 files, integrity manifest and verified restore procedure; these files contain VPN credentials.
- Verify that replacement files are syntactically valid with **router Python 3.9** and `sh -n` before any service restart.
- Roll back all coordinated appliance/watchdog files together upon any functional failure. Rollback must not reset the existing runtime VPN/WAN mode or firewall rules unexpectedly.
- Stage and validate **without** restarting sing-box or watchdog. Rollout/restart/merge require separate explicit owner authorization.

## Post-rollout acceptance checks

Compare before/after for:
- 15 saved profiles (none removed during deployment), active VLESS server, route mode.
- LAN VPN: `ip rule` priority 1000, table 100 `maxvpn0`, `MAXVPN_LAN_FORWARD`, IPv6 drop.
- DIRECT policy: mark `0x64/0xff`, table 200, NAT `MAXVPN_DIRECT_NAT`, `MAXVPN_DIRECT` count.
- Printer subnet/rule/SNAT; local printer accessibility.
- Active sing-box + watchdog and health of UI/API.
- Controlled negative tests (only in isolated environment): bulk delete rollback, watchdog racing against route switch, API timeout and explicit WAN-fallback policy.

**Do not test bulk deletion on the production router.** With WAN fallback enabled, successful deletion from VLESS is explicitly allowed to move LAN straight to WAN and remove every VPN profile.
