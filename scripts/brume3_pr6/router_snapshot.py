#!/usr/bin/env python3
"""GL-MT5000 CN: guarded, secret-safe PR6 snapshot and restore controller.

Run through run.sh over ssh (Python 3.9 compatible). No API requests, service
restart or routing mutation occurs in preflight, backup or verify. The restore
path is disabled until an approved deployment writes its receipt.
"""
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/opt/maxvpn-appliance/backups/pr6-gated")
TARGETS = (
    "/opt/maxvpn-appliance/server.py",
    "/opt/maxvpn-appliance/vless_control.py",
    "/opt/maxvpn-appliance/vless_subscription.py",
    "/www/maxvpn/index.html",
    "/usr/bin/maxvpn-vless-watchdog",
    "/usr/bin/vpn-lan-on",
    "/usr/bin/vpn-lan-off",
    "/usr/bin/vpn-lan-vless-on",
    "/usr/bin/vpn-lan-vless-stop",
    "/etc/init.d/maxvpn-sing-box",
    "/etc/init.d/maxvpn-vless-watchdog",
    "/etc/maxvpn/firewall.user",
    "/etc/hotplug.d/iface/99-lan-vpn",
    "/etc/hotplug.d/iface/99-maxvpn-restore-routing",
    "/etc/maxvpn/vless-profiles.json",
    "/etc/maxvpn/sing-box-vless.json",
    "/etc/maxvpn/runtime-mode",
    "/opt/maxvpn-appliance/data/vless-delay-history.json",
    "/opt/maxvpn-appliance/data/vless-selection-history.sqlite3",
    "/opt/maxvpn-appliance/data/vless-availability.sqlite3",
)
# A receipt can authorize rollback of only these deployed *code* paths.
# Runtime mode, profiles, routing helpers, firewall, printer and DNS are
# deliberately excluded from automatic restoration.
RESTORABLE = frozenset((
    "/opt/maxvpn-appliance/server.py",
    "/opt/maxvpn-appliance/vless_control.py",
    "/opt/maxvpn-appliance/vless_subscription.py",
    "/www/maxvpn/index.html",
    "/usr/bin/maxvpn-vless-watchdog",
    "/usr/bin/vpn-lan-vless-stop",
))
BASELINE = {
    "/opt/maxvpn-appliance/server.py":
        "3b3919434698d31244cec87247d10eafacf31eba1f0a8fa3fe539d0cf07c53f5",
    "/opt/maxvpn-appliance/vless_control.py":
        "ae97cedaa795f06af99e898b92bf80cb06f1c40558213b353df949d5ec772189",
    "/opt/maxvpn-appliance/vless_subscription.py":
        "03d1f623034bc02861f593866fb827d41146c5e343f7f65e5a4070fb4ceb5c64",
    "/www/maxvpn/index.html":
        "c50d460900af781e5c32f740eab2484da1defe10eaf95ab341231ef906bc3649",
}
ID_RE = re.compile(r"^pr6-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")


def fail(message):
    raise RuntimeError(message)


def regular_file(path):
    try:
        st = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(st.st_mode):
        fail("Refuse nonregular file: " + str(path))
    return st


def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def cmd(*args):
    return subprocess.run(args, capture_output=True, text=True, check=False)


def route_preflight():
    expected_files = 0
    errors = []
    for name, digest in BASELINE.items():
        path = Path(name)
        st = regular_file(path)
        if st is None or sha256(path) != digest:
            errors.append("Baseline SHA mismatch: " + name)
        else:
            expected_files += 1
    if Path("/etc/maxvpn/runtime-mode").read_text().strip() != "vless":
        errors.append("Unexpected LAN traffic mode")
    if not Path("/usr/bin/flock").is_file():
        errors.append("No /usr/bin/flock")
    for family in ("iptables", "ip6tables"):
        chain = "MAXVPN_LAN_FORWARD" if family == "iptables" else "MAXVPN_LAN6_FORWARD"
        if cmd(family, "-C", "forwarding_rule", "-j", chain).returncode:
            errors.append("Missing " + family + " forwarding hook")
    if cmd("ip", "-4", "route", "show", "table", "100").stdout.find(
        "default dev maxvpn0"
    ) < 0:
        errors.append("VLESS table 100 default route missing")
    if cmd("ip", "-4", "route", "show", "table", "200").stdout.find(
        "dev eth1"
    ) < 0:
        errors.append("DIRECT table 200 WAN route missing")
    if cmd("ip", "-4", "rule", "show").stdout.find(
        "to 192.168.31.137"
    ) < 0:
        errors.append("Printer legacy rule missing")
    try:
        profiles = json.loads(
            Path("/etc/maxvpn/vless-profiles.json").read_text(encoding="utf-8")
        )
        count = len(profiles.get("profiles", []))
    except (OSError, ValueError, AttributeError, TypeError):
        errors.append("VLESS profile count unreadable")
        count = None
    print("PREFLIGHT_MODE=vless")
    print("BASELINE_MATCH_COUNT=" + str(expected_files) + "/4")
    print("VLESS_PROFILES=" + str(count) if count is not None else "VLESS_PROFILES=UNKNOWN")
    print("VLESS_STOP_HELPER=" + (
        "PRESENT" if Path("/usr/bin/vpn-lan-vless-stop").exists()
        else "MISSING_EXPECTED_ON_BASELINE"
    ))
    for problem in errors:
        print("BLOCKER=" + problem)
    print("PREFLIGHT=" + ("PASS" if not errors else "BLOCKED"))
    return 0 if not errors else 2


def private_base(create):
    if BASE.is_symlink():
        fail("Backup root is a symlink")
    if create and not BASE.exists():
        BASE.mkdir(parents=True, mode=0o700)
    if not BASE.is_dir():
        fail("Backup root is missing or not a directory")
    st = BASE.lstat()
    if st.st_mode & 0o077:
        fail("Backup root must be private (0700)")
    return BASE


def backup():
    if os.geteuid() != 0:
        fail("Requires root")
    root = private_base(True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ident = "pr6-" + stamp + "-" + os.urandom(4).hex()
    working = root / (ident + ".incomplete")
    final = root / ident
    working.mkdir(mode=0o700)
    entries = []
    try:
        for i, target in enumerate(TARGETS):
            src = Path(target)
            info = regular_file(src)
            entry = {"path": target, "exists": info is not None}
            if info is not None:
                name = "{:03d}.blob".format(i)
                dest = working / name
                # Copy file content only; no secret values are printed.
                with src.open("rb") as read, dest.open("xb") as write:
                    os.chmod(dest, 0o600)
                    while True:
                        chunk = read.read(1024 * 1024)
                        if not chunk:
                            break
                        write.write(chunk)
                    write.flush()
                    os.fsync(write.fileno())
                entry.update({
                    "blob": name,
                    "sha256": sha256(dest),
                    "mode": stat.S_IMODE(info.st_mode),
                    "uid": info.st_uid,
                    "gid": info.st_gid,
                })
            entries.append(entry)
        manifest = {
            "schema": 1,
            "backup_id": ident,
            "created_utc": stamp,
            "files": entries,
            "automated_restore_only": sorted(RESTORABLE),
        }
        manifest_file = working / "manifest.json"
        with manifest_file.open("x", encoding="utf-8") as output:
            os.chmod(manifest_file, 0o600)
            json.dump(manifest, output, indent=2, ensure_ascii=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        digest = sha256(manifest_file)
        (working / "manifest.sha256").write_text(digest + "\n")
        os.chmod(working / "manifest.sha256", 0o600)
        working.rename(final)
        verify(ident)
        print("BACKUP_ID=" + ident)
        print("BACKUP_PATH=" + str(final))
        print("BACKUP_VERIFIED=YES")
        return 0
    except Exception:
        # Keep incomplete files private, but do not claim a successful backup.
        fail("Backup incomplete. Inspect private directory: " + str(working))


def resolve_backup(ident):
    if not ID_RE.fullmatch(ident):
        fail("Invalid backup ID")
    root = private_base(False)
    snapshot = root / ident
    if snapshot.is_symlink() or not snapshot.is_dir():
        fail("Backup is missing or is a symlink")
    if snapshot.stat().st_mode & 0o077:
        fail("Snapshot permissions are not private")
    return snapshot


def verify(ident):
    path = resolve_backup(ident)
    manifest_path = path / "manifest.json"
    digest_path = path / "manifest.sha256"
    for item in (manifest_path, digest_path):
        if regular_file(item) is None:
            fail("Missing manifest component")
    if sha256(manifest_path) != digest_path.read_text().strip():
        fail("Manifest digest mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("backup_id") != ident:
        fail("Unsupported or incorrect backup manifest")
    files = manifest.get("files")
    if not isinstance(files, list) or [e.get("path") for e in files] != list(TARGETS):
        fail("Snapshot file list mismatch")
    for index, entry in enumerate(files):
        if not entry["exists"]:
            continue
        name = "{:03d}.blob".format(index)
        if entry.get("blob") != name or not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")):
            fail("Invalid backup entry")
        blob = path / name
        info = regular_file(blob)
        if info is None or info.st_mode & 0o077:
            fail("Backup blob missing or exposed")
        if sha256(blob) != entry["sha256"]:
            fail("Backup checksum mismatch")
    print("VERIFIED_BACKUP=" + ident)
    return manifest


def restore(ident, confirmation):
    # This command is deliberately unavailable for a baseline-only snapshot.
    # A later, approved installer must create a private deployment receipt
    # containing the post-install digests of each changed code file.
    if confirmation != "RESTORE-" + ident:
        fail("Explicit restore confirmation missing")
    snapshot = resolve_backup(ident)
    manifest = verify(ident)
    receipt_path = snapshot / "deployment-receipt.json"
    if regular_file(receipt_path) is None:
        fail("No approved deployment receipt: restore remains disabled")
    receipt = json.loads(receipt_path.read_text())
    records = receipt.get("replaced", [])
    if not records:
        fail("No recorded replacement files")
    originals = {f["path"]: f for f in manifest["files"]}
    for record in records:
        target = record.get("path")
        expected = record.get("sha256_after")
        if target not in RESTORABLE or not re.fullmatch(r"[0-9a-f]{64}", expected or ""):
            fail("Unsafe restore receipt")
        original = originals[target]
        current = Path(target)
        cur = regular_file(current)
        if original["exists"]:
            if cur is None or sha256(current) not in (original["sha256"], expected):
                fail("Current live file differs from the approved deployment: " + target)
        elif cur is not None and sha256(current) != expected:
            fail("Unexpected new file differs from the deployment: " + target)
    # Stage every original before mutating live names.
    prepared = []
    try:
        for record in records:
            target = Path(record["path"])
            original = originals[record["path"]]
            if original["exists"]:
                fd, temp = tempfile.mkstemp(prefix=".pr6-restore-", dir=str(target.parent))
                try:
                    with os.fdopen(fd, "wb") as dest, (snapshot / original["blob"]).open("rb") as src:
                        for chunk in iter(lambda: src.read(1024 * 1024), b""):
                            dest.write(chunk)
                        dest.flush()
                        os.fsync(dest.fileno())
                    os.chmod(temp, original["mode"])
                    os.chown(temp, original["uid"], original["gid"])
                except Exception:
                    os.unlink(temp)
                    raise
                prepared.append((target, temp))
            else:
                prepared.append((target, None))
        for target, tmp in prepared:
            if tmp is None:
                if target.exists():
                    target.unlink()
            else:
                os.replace(tmp, str(target))
        print("RESTORED_FILES=" + str(len(prepared)))
        print("SERVICE_RESTART=NOT_PERFORMED")
        print("RUNTIME_MODE_AND_FIREWALL=NOT_MODIFIED")
        return 0
    finally:
        for _, temp in prepared:
            if temp and os.path.exists(temp):
                os.unlink(temp)


def main():
    if len(sys.argv) < 2:
        fail("Usage: preflight | backup | verify ID | restore ID CONFIRMATION")
    action = sys.argv[1]
    if action == "preflight" and len(sys.argv) == 2:
        return route_preflight()
    if action == "backup" and len(sys.argv) == 2:
        return backup()
    if action == "verify" and len(sys.argv) == 3:
        verify(sys.argv[2])
        return 0
    if action == "restore" and len(sys.argv) == 4:
        return restore(sys.argv[2], sys.argv[3])
    fail("Unsupported operation or arguments")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print("ERROR=" + str(error), file=sys.stderr)
        sys.exit(2)
