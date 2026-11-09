# MaxVPN Smart Routing — Live IPv4 Verification

Date: 2026-10-29
Router: GL-MT5000, OpenWrt
WAN interface: eth1
WAN IPv4: 46.48.56.64
LAN interface: br-lan
IPv6: Not tested; ISP does not provide IPv6.
Configuration changes: None during verification.

## 1. Automated IPv4 audit

Domains:
- mts.ru
- rzd.ru
- wialonlocal.online

Result:
PASS: all required IPv4 checks passed.
No runtime configuration was changed.

Verified:
- MAXVPN_DIRECT exists and contains the queried DNS A records.
- MAXVPN_DIRECT_STATIC exists; an empty set is valid.
- fwmark 0x64/0xff selects routing table 200.
- Table 200 has a default route via 46.48.56.1 on eth1.
- The mangle PREROUTING rules for dynamic and static DIRECT sets exist.

Audit output:
exports/diagnostics/maxvpn-smart-routing-ipv4-audit-20261029-222114.log
exports/diagnostics/maxvpn-smart-routing-ipv4-audit-20261029-222114.md

## 2. Live HTTPS packet captures

### mts.ru

Destination IPv4: 178.248.238.27

Observed on eth1:
- TCP SYN and SYN-ACK.
- Bidirectional data exchange.
- TCP connection teardown.
- 18 packets captured; 0 packets dropped by kernel.

A separate capture on br-lan observed:
- LAN source 192.168.8.231.
- Destination 178.248.238.27:443.
- Bidirectional TCP data exchange.
- 18 packets captured; 0 packets dropped by kernel.

A separate WAN capture observed the connection to the same destination through eth1:
- WAN source 46.48.56.64.
- Destination 178.248.238.27:443.
- 18 packets captured; 0 packets dropped by kernel.

Note: the LAN and WAN captures were performed during separate HTTPS requests,
not as one synchronized capture of the same TCP flow.

### rzd.ru

Tested IPv4: 212.164.138.131

Observed on eth1:
- TCP handshake completed.
- Bidirectional data exchange.
- Server sent TCP RST at the end of the observed exchange.
- 21 packets captured; 0 packets dropped by kernel.

This confirms packet exchange with the destination, but does not establish
that the HTTP request completed successfully.

### wialonlocal.online

Tested IPv4: 94.242.50.237

Observed on eth1:
- TCP handshake completed.
- Bidirectional data exchange.
- TCP connection teardown.
- 11 packets captured; 0 packets dropped by kernel.

The Windows client reported a certificate name mismatch. Therefore, successful
certificate validation and fully valid HTTPS were not established.

## 3. Routing and marking observations

- `ip -4 route get 178.248.238.27 mark 0x64` selected table 200 via eth1.
- The dynamic MAXVPN_DIRECT mangle rule was present.
- Its displayed packet counter changed from approximately 269K to 270K.
- The counter is shared and displayed in rounded units; the exact increment
  attributable to the test request cannot be determined.
- The static DIRECT set was empty, and its rule counter was zero.

## 4. Conclusion

The automated audit passed for all three domains.
Live captures independently confirmed bidirectional packet exchange through
eth1 for mts.ru, rzd.ru, and wialonlocal.online.

These observations support the conclusion that the tested destinations were
reachable through the WAN interface during the tests.

Limitations:
- The captures do not by themselves prove that the specific packets were
  marked by MAXVPN_DIRECT.
- The LAN and WAN captures for mts.ru were not synchronized to the same flow.
- HTTP/TLS application-level success was not established for every domain.
- No routing, firewall, DNS, VPN, or IPv6 configuration was changed.

## 5. Recommended follow-up

1. Review DNS reconciliation when the DIRECT domain policy becomes empty.
2. Verify that stale DNS-owned addresses are removed while static DIRECT
   entries remain preserved.
3. If per-flow marking proof is required, design a narrowly scoped,
   reversible diagnostic that does not reset existing counters or alter
   production routing policy.
