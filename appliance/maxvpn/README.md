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

## HTTPS VLESS subscription import (draft)

The appliance installs `vless_subscription.py` alongside `vless_control.py`
and `server.py` in `/opt/maxvpn-appliance/`. Copy all three modules when
testing this branch on an isolated appliance; deploying only `server.py` will
not work.

The web UI includes a separate **Импорт из HTTPS-подписки** form. It performs
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
deleted. The existing 50-profile limit applies.

Treat subscription URLs as credentials. Do not put full URLs in issues,
commit messages, console logs or screenshots. Downloader validates DNS answers
and certificate, pins connections to public addresses, rejects cross-host
redirects and limits response size. Production deployment requires CI,
isolated OpenWrt validation and end-to-end review of the provider's actual
subscription format.
