# MaxVPN Smart Routing diagnostics

## Read-only IPv4 audit with archived report

From the repository root:

```bash
bash scripts/run_maxvpn_smart_routing_report.sh mts.ru
```

This saves a timestamped full transcript (`.log`) and a compact Markdown index
(`.md`) under `exports/diagnostics/`. Multiple domains can be supplied.

To include an auxiliary route lookup that simulates a packet arriving from a
real LAN client, first find that Windows device's LAN IPv4 address with
`ipconfig`, then run:

```bash
MAXVPN_LAN_CLIENT_IP=192.168.8.X bash scripts/run_maxvpn_smart_routing_report.sh mts.ru
```

Replace `192.168.8.X` with the client's actual IPv4 address, not the router's
`192.168.8.1` address. Without this optional value, the report marks the
source-aware lookup `N/A`; this does not make the required DIRECT audit fail.

## Interactive live capture

```bash
bash scripts/maxvpn_smart_routing_ipv4_diagnostic.sh capture mts.ru
```

Run the printed `curl.exe` command from a separate PowerShell on a LAN-connected
device, then press Ctrl+C in the capture terminal. The capture output is shown
live; it does not write a packet-capture file. The report wrapper intentionally
runs audit mode only so an interactive Ctrl+C cannot interrupt report saving.

## Safety boundary

The scripts read runtime state only. They do not change routes, ipsets, mangle
rules, UCI, VPN mode or counters. IPv6 is explicitly out of scope because the
ISP does not provide it.
