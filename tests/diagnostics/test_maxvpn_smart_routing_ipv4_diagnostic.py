"""Offline regression tests for the read-only MaxVPN IPv4 diagnostic scripts.

All router commands are mocked through PATH and a fake ssh executable. These
checks never connect to a router and never mutate routes, ipsets, firewall, or
packet counters.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTIC = REPO_ROOT / "scripts" / "maxvpn_smart_routing_ipv4_diagnostic.sh"
REPORT_WRAPPER = REPO_ROOT / "scripts" / "run_maxvpn_smart_routing_report.sh"


MOCK_COMMANDS = {
    "ssh": r"""#!/bin/sh
set -eu
if [ "$#" -lt 2 ]; then
  echo "mock ssh: missing remote command" >&2
  exit 2
fi
host="$1"
shift
if [ -n "${MOCK_SSH_CALL_LOG:-}" ]; then
  printf '%s\n' "$host $*" >> "$MOCK_SSH_CALL_LOG"
fi
exec "$@"
""",
    "nslookup": r"""#!/bin/sh
set -eu
domain="$1"
case " ${MOCK_DNS_NXDOMAIN:-} " in
  *" $domain "*)
    echo "** server can't find $domain: NXDOMAIN" >&2
    exit 1
    ;;
esac
case "$domain" in
  mts.ru)
    cat <<'OUT'
Server: 127.0.0.1
Address 1: 127.0.0.1 localhost

Name: mts.ru
Address 1: 192.0.2.10
Address 2: 198.51.100.20
OUT
    ;;
  rzd.ru)
    cat <<'OUT'
Server: 127.0.0.1
Address 1: 127.0.0.1 localhost

Name: rzd.ru
Address 1: 203.0.113.30
OUT
    ;;
  wialonlocal.online)
    cat <<'OUT'
Server: 127.0.0.1
Address 1: 127.0.0.1 localhost

Name: wialonlocal.online
Address 1: 192.0.2.40
OUT
    ;;
  *)
    echo "** server can't find $domain: NXDOMAIN" >&2
    exit 1
    ;;
esac
""",
    "ipset": r"""#!/bin/sh
set -eu
command="$1"
set_name="${2:-}"
case "$command:$set_name" in
  list:MAXVPN_DIRECT)
    cat <<'OUT'
Name: MAXVPN_DIRECT
Type: hash:ip
Revision: 4
Header: family inet hashsize 1024 maxelem 65536
Number of entries: 4
Members:
192.0.2.10
198.51.100.20
203.0.113.30
192.0.2.40
OUT
    ;;
  list:MAXVPN_DIRECT_STATIC)
    cat <<'OUT'
Name: MAXVPN_DIRECT_STATIC
Type: hash:ip
Revision: 4
Header: family inet hashsize 1024 maxelem 65536
Number of entries: 0
OUT
    ;;
  test:MAXVPN_DIRECT)
    address="${3:-}"
    case " ${MOCK_DIRECT_OMIT:-} " in
      *" $address "*)
        echo "ipset v7.15: The set with the given name does not exist or is empty" >&2
        exit 1
        ;;
    esac
    case "$address" in
      192.0.2.10|198.51.100.20|203.0.113.30|192.0.2.40) exit 0 ;;
      *) echo "$address is NOT in set MAXVPN_DIRECT" >&2; exit 1 ;;
    esac
    ;;
  *)
    echo "unexpected mock ipset command: $*" >&2
    exit 2
    ;;
esac
""",
    "ip": r"""#!/bin/sh
set -eu
args="$*"
case "$args" in
  "-4 rule show")
    echo '0: from all lookup local'
    echo '100: from all fwmark 0x64/0xff lookup 200'
    echo '1000: from all iif br-lan lookup 100'
    ;;
  "-4 route show table 200")
    echo 'default via 46.48.56.1 dev eth1'
    echo '192.168.8.0/24 dev br-lan proto kernel scope link src 192.168.8.1'
    ;;
  "-4 route get 192.0.2.10 mark 0x64")
    echo '192.0.2.10 via 46.48.56.1 dev eth1 table 200 src 46.48.56.64 mark 0x64 uid 0 cache'
    ;;
  "-4 route get 198.51.100.20 mark 0x64")
    echo '198.51.100.20 via 46.48.56.1 dev eth1 table 200 src 46.48.56.64 mark 0x64 uid 0 cache'
    ;;
  "-4 route get 203.0.113.30 mark 0x64")
    echo '203.0.113.30 via 46.48.56.1 dev eth1 table 200 src 46.48.56.64 mark 0x64 uid 0 cache'
    ;;
  "-4 route get 192.0.2.40 mark 0x64")
    echo '192.0.2.40 via 46.48.56.1 dev eth1 table 200 src 46.48.56.64 mark 0x64 uid 0 cache'
    ;;
  "-4 -o addr show dev br-lan")
    echo '7: br-lan inet 192.168.8.1/24 brd 192.168.8.255 scope global br-lan'
    ;;
  "-4 route get "*" from "*" iif br-lan")
    set -- $args
    address="$4"
    source="$6"
    echo "$address from $source via 192.168.8.1 dev br-lan table 100"
    ;;
  *)
    echo "unexpected mock ip command: $args" >&2
    exit 2
    ;;
esac
""",
    "iptables": r"""#!/bin/sh
set -eu
case "$*" in
  "-t mangle -S")
    cat <<'OUT'
-P PREROUTING ACCEPT
-A PREROUTING -i br-lan -m set --match-set MAXVPN_DIRECT dst -j MARK --set-xmark 0x64/0xff
-A PREROUTING -i br-lan -m set --match-set MAXVPN_DIRECT_STATIC dst -j MARK --set-xmark 0x64/0xff
OUT
    ;;
  "-t mangle -L PREROUTING -nvx --line-numbers")
    cat <<'OUT'
Chain PREROUTING (policy ACCEPT 0 packets, 0 bytes)
num      pkts      bytes target     prot opt in     out     source               destination
1      130830 49000158 MARK       all  --  br-lan *       0.0.0.0/0            0.0.0.0/0            match-set MAXVPN_DIRECT dst MARK xset 0x64/0xff
2           0        0 MARK       all  --  br-lan *       0.0.0.0/0            0.0.0.0/0            match-set MAXVPN_DIRECT_STATIC dst MARK xset 0x64/0xff
OUT
    ;;
  *)
    echo "unexpected mock iptables command: $*" >&2
    exit 2
    ;;
esac
""",
}


class SmartRoutingDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DIAGNOSTIC.is_file():
            raise RuntimeError(f"Diagnostic script not found: {DIAGNOSTIC}")
        if not REPORT_WRAPPER.is_file():
            raise RuntimeError(f"Report wrapper not found: {REPORT_WRAPPER}")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="maxvpn-smart-routing-test-")
        self.temp_path = Path(self.temp.name)
        self.bin_path = self.temp_path / "bin"
        self.bin_path.mkdir()
        for name, content in MOCK_COMMANDS.items():
            target = self.bin_path / name
            target.write_text(content, encoding="utf-8")
            target.chmod(0o755)
        self.ssh_call_log = self.temp_path / "ssh-calls.log"
        self.report_dir = self.temp_path / "reports"
        self.env = os.environ.copy()
        self.env.update(
            {
                "PATH": f"{self.bin_path}{os.pathsep}{self.env.get('PATH', '')}",
                "MOCK_SSH_CALL_LOG": str(self.ssh_call_log),
                "MAXVPN_ROUTER": "mock-router",
            }
        )
        for key in ("MOCK_DNS_NXDOMAIN", "MOCK_DIRECT_OMIT"):
            self.env.pop(key, None)
        self.env.pop("MAXVPN_LAN_CLIENT_IP", None)
        self.env.pop("MAXVPN_REPORT_DIR", None)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_bash(
        self, script: Path, *args: str, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", str(script), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    def test_audit_accepts_multiple_domains_and_multiple_a_records(self) -> None:
        result = self.run_bash(DIAGNOSTIC, "audit", "mts.ru", "rzd.ru")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = result.stdout
        for expected in (
            "Domains: mts.ru, rzd.ru",
            "-- mts.ru --",
            "-- rzd.ru --",
            "DNS A record for mts.ru via router resolver: 192.0.2.10, 198.51.100.20",
            "DNS A record for rzd.ru via router resolver: 203.0.113.30",
            "192.0.2.10 belongs to MAXVPN_DIRECT",
            "198.51.100.20 belongs to MAXVPN_DIRECT",
            "203.0.113.30 belongs to MAXVPN_DIRECT",
            "PASS: all required IPv4 checks passed.",
            "IPv6: N/A",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, output)

    def test_dns_failure_is_reported_and_returns_nonzero(self) -> None:
        result = self.run_bash(
            DIAGNOSTIC,
            "audit",
            "mts.ru",
            "rzd.ru",
            extra_env={"MOCK_DNS_NXDOMAIN": "rzd.ru"},
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "[FAIL] DNS A record for rzd.ru via router resolver", result.stdout
        )
        self.assertIn("FAIL:", result.stdout)

    def test_dns_address_missing_from_direct_set_is_a_failure(self) -> None:
        result = self.run_bash(
            DIAGNOSTIC,
            "audit",
            "rzd.ru",
            extra_env={"MOCK_DIRECT_OMIT": "203.0.113.30"},
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("[FAIL] 203.0.113.30 belongs to MAXVPN_DIRECT", result.stdout)

    def test_source_aware_lookup_is_attempted_only_for_client_on_br_lan(self) -> None:
        result = self.run_bash(
            DIAGNOSTIC,
            "audit",
            "mts.ru",
            extra_env={"MAXVPN_LAN_CLIENT_IP": "192.168.8.44"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "source-aware unmarked LAN lookup for 192.0.2.10 from 192.168.8.44",
            result.stdout,
        )
        self.assertIn("via 192.168.8.1 dev br-lan table 100", result.stdout)

    def test_invalid_domain_is_rejected_before_ssh(self) -> None:
        result = self.run_bash(DIAGNOSTIC, "audit", "not_a_valid_domain")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("Invalid domain name", result.stderr)
        self.assertFalse(
            self.ssh_call_log.exists(), "SSH must not run for invalid input"
        )

    def test_report_wrapper_archives_a_multi_domain_audit(self) -> None:
        result = self.run_bash(
            REPORT_WRAPPER,
            "mts.ru",
            "rzd.ru",
            extra_env={"MAXVPN_REPORT_DIR": str(self.report_dir)},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        logs = list(self.report_dir.glob("*.log"))
        summaries = list(self.report_dir.glob("*.md"))
        self.assertEqual(len(logs), 1, list(self.report_dir.iterdir()))
        self.assertEqual(len(summaries), 1, list(self.report_dir.iterdir()))
        log_text = logs[0].read_text(encoding="utf-8")
        summary_text = summaries[0].read_text(encoding="utf-8")
        self.assertIn("-- mts.ru --", log_text)
        self.assertIn("-- rzd.ru --", log_text)
        self.assertIn("Domains: mts.ru rzd.ru", summary_text)
        self.assertIn("Result: **PASS**", summary_text)
        self.assertIn("IPv6: N/A", summary_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
