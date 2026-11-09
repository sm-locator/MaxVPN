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
