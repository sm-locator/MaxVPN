# MaxVPN Appliance

Standalone MaxVPN management UI/API for GL.iNet Brume 3.

## Runtime paths

The appliance server is installed as:

- `/opt/maxvpn-appliance/server.py`

The web UI is served from:

- `/www/maxvpn/`

The appliance API listens on:

- `127.0.0.1:8787`

## VPN control

The appliance API controls LAN traffic through the persistent helper scripts:

- `/usr/bin/vpn-lan-on`
- `/usr/bin/vpn-lan-off`

`POST /api/appliance/v1/vpn/start` enables VPN LAN routing.

`POST /api/appliance/v1/vpn/stop` switches LAN traffic to WAN.

The VPN API response includes `traffic_mode`:

- `vpn`
- `wan`

## Important

The appliance must use the persistent `vpn-lan-on` / `vpn-lan-off`
helpers instead of calling `ifup` / `ifdown` directly. This keeps
WireGuard interface state and LAN routing policy synchronized.

## VLESS link and HTTPS subscription import (draft)

The appliance installs `vless_subscription.py` alongside `vless_control.py`
and `server.py` in `/opt/maxvpn-appliance/`. Copy all three modules when
testing this branch on an isolated appliance; deploying only `server.py` will
not work.

The UI supports pasting one or several direct `vless://` links into **Импорт серверов**
(via `POST /api/appliance/v1/vless/import`) and a separate
**Импорт из HTTPS-подписки** form. It performs
read-only preview via `POST /api/appliance/v1/vless/subscription/preview`.
After confirmation the UI calls
`POST /api/appliance/v1/vless/subscription/import`, providing the original URL,
user-agent preset and the SHA-256 digest returned by preview. The server
re-downloads the subscription and refuses import if its content changed.
Neither operation modifies the live sing-box configuration or LAN routes;
existing **Применить** is still required.

This is a **one-time** import, not subscription registration or auto-refresh.
Supported input: HTTPS-delivered raw/Base64 VLESS URI lists and Xray/HAPP JSON
with VLESS outbounds. Only VLESS/TCP with REALITY or no TLS is compatible with
the current runtime. Incompatible protocols and transports are reported in the
preview instead of being silently converted. Existing saved profiles are not
deleted. The existing 50-profile limit applies. Malformed placeholder nodes such as
`0.0.0.0:1`, loopback, reserved and other non-public literal IP endpoints are
rejected for both direct URI/JSON imports and subscription entries. Preview
reports unsupported nodes and duplicate aliases separately, and imports only
unique valid connections. Do not treat `sing-box check` as a live connectivity
test. A provider may return placeholder nodes when authentication or device
registration is missing; obtain an authorized subscription for the router.

Treat subscription URLs as credentials. Do not put full URLs in issues,
commit messages, console logs or screenshots. Downloader validates DNS answers
and certificate, pins connections to public addresses, rejects cross-host
redirects and limits response size. Production deployment requires CI,
isolated OpenWrt validation and end-to-end review of the provider's actual
subscription format.


### VLESS profile removal and availability

The appliance dashboard can clear all saved VLESS profiles, including disabled
profiles. The collection endpoint is `DELETE /api/appliance/v1/vless/profiles`.
The JSON body requires `confirm: true` and the current `delete_revision` from
the VLESS state. When LAN uses VLESS, a transition to direct WAN also requires
`allow_wan: true` and the existing WAN fallback policy. With Kill Switch on,
select a protected LAN route before clearing the profiles. A successful clear
stops sing-box, disables its autostart and clears the installed configuration,
pinned selection, fallback recovery state and per-profile measurement history.
The existing private profile backup policy applies.

The selection-history API reports per-profile availability from manual BRUME 3
checks and sing-box URLTest observations in measurement-time order. An open
outage begins with the first confirmed failure after the latest success.
When Clash history is empty, the monitor asks the local sing-box delay endpoint
for confirmation at most once per configured URLTest interval for that tag.
A failed probe (HTTP 503/504) starts or continues an outage. An unreachable API,
unknown tag or malformed response supplies no measurement. Existing histories
contribute their recorded evidence. Gaps in legacy summaries stay unknown.

When WAN fallback is explicitly enabled (Kill Switch OFF), two consecutive
monitor passes where *all* required profile probes fail to connect to the local
Clash API (curl connection/timeout errors) trigger WAN fallback as a runtime
control-plane outage. This does not mark each VLESS server as failed. Partial
API failures or malformed/unknown responses never count towards this failover.
The profile outage journal remains based only on confirmed probe outcomes.
During a VLESS-mode bulk delete, an error before committing the empty profile
store attempts to restore the previous VLESS route; after commit the route is
never restored using removed profiles.

Bulk removal holds the same `/opt/maxvpn-appliance/run/apply.lock` as the
appliance Smart Routing server across the LAN transition, store commit, and
rollback. The installed watchdog must also respect this lock: if the legacy
unlocked `/usr/bin/maxvpn-vless-watchdog` is present, VLESS-mode bulk removal
is rejected before changing any route or profile. An isolated candidate matching
the inspected GL-MT5000 watchdog is staged in
`appliance/maxvpn/compat/brume3-watchdog-locked.sh`. It is **not** installed
automatically. Follow the device-specific deployment gate at
`docs/deployments/brume3-vless-bulk-delete-20261121.md`; never blindly replace
the existing live routing helpers or firewall setup.
