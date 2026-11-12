"""Real browser/API/PostgreSQL/SSH/OpenWrt integration, confined to a local lab."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import time
import urllib.request

from openwrt_lab import Lab
from verify_openwrt_lab import no_leaks, setup, verify

ROOT = Path(__file__).resolve().parents[1]


def download(url):
    for attempt in range(3):
        try:
            return urllib.request.urlopen(url, timeout=30).read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(1)


def install_lab_dependencies(lab, state):
    required = set()
    if "/usr/bin/curl" not in lab.command("router", "command -v curl || true"):
        required.update({"curl", "libcurl4", "libnghttp2-14", "ca-bundle"})
    version = lab.command("router", "dnsmasq --version")
    import re

    needs_dnsmasq = not re.search(
        r"(?<![\w-])ipset(?![\w-])", version.split("Compile time options:", 1)[-1]
    )
    if needs_dnsmasq:
        required.update(
            {
                "dnsmasq-full",
                "libnettle8",
                "libgmp10",
                "libnetfilter-conntrack3",
                "libnfnetlink0",
                "libmnl0",
                "kmod-nf-conntrack-netlink",
            }
        )
    if not required:
        return
    release = lab.command("router", "cat /etc/openwrt_release; uname -m")
    if "21.02.7" not in release or "x86_64" not in release:
        raise RuntimeError(
            "Provision curl and dnsmasq with ipset before running the live test"
        )
    # The existing lab images are OpenWrt 21.02.7 x86-64. Download their real
    # HTTP client on the host; the guests remain without an outside uplink.
    installed = lab.command("router", "opkg list-installed")
    installed_names = {
        line.split(" - ", 1)[0] for line in installed.splitlines() if " - " in line
    }
    required -= installed_names
    base = "https://archive.openwrt.org/releases/21.02.7/"
    feeds = [
        "packages/x86_64/base",
        "packages/x86_64/packages",
        "targets/x86/64/packages",
    ]
    packages = {}
    for feed in feeds:
        listing = gzip.decompress(download(base + feed + "/Packages.gz")).decode()
        for block in listing.split("\n\n"):
            fields = dict(
                line.split(": ", 1)
                for line in block.splitlines()
                if ": " in line and not line.startswith(" ")
            )
            if fields.get("Package") in required:
                packages[fields["Package"]] = (feed, fields)
    if set(packages) != required:
        raise RuntimeError("Required lab package metadata is unavailable")
    directory = state / "packages"
    directory.mkdir(exist_ok=True)
    lab.command("router", "mkdir -p /tmp/live-e2e-packages")
    manifest = []
    for name, (feed, fields) in packages.items():
        url = base + feed + "/" + fields["Filename"]
        cached = directory / fields["Filename"]
        data = cached.read_bytes() if cached.exists() else download(url)
        if hashlib.sha256(data).hexdigest() != fields["SHA256sum"]:
            raise RuntimeError("Lab package checksum mismatch")
        (directory / fields["Filename"]).write_bytes(data)
        metadata = json.loads((state / "state.json").read_text())
        remote_path = "/tmp/live-e2e-packages/" + fields["Filename"]
        run(
            [
                "scp",
                "-O",
                "-F",
                str(state / "ssh_config"),
                "-P",
                str(metadata["ssh_port"]),
                "-i",
                str(state / "id_ed25519"),
                "-o",
                "BatchMode=yes",
                str(cached),
                "root@127.0.0.1:" + remote_path,
            ]
        )
        if fields["SHA256sum"] not in lab.command("router", "sha256sum " + remote_path):
            raise RuntimeError("Transferred lab package checksum mismatch")
        manifest.append({"package": name, "url": url, "sha256": fields["SHA256sum"]})
        print("Transferred verified lab dependency: " + name, flush=True)
    (state / "packages.json").write_text(json.dumps(manifest, indent=2))
    if needs_dnsmasq:
        lab.command(
            "router",
            "cp /etc/config/dhcp /tmp/live-e2e-dhcp && /etc/init.d/dnsmasq stop && opkg remove dnsmasq",
        )
    lab.command(
        "router",
        "opkg install /tmp/live-e2e-packages/*.ipk && command -v curl",
        timeout=45,
    )
    if needs_dnsmasq:
        lab.command(
            "router",
            "cp /tmp/live-e2e-dhcp /etc/config/dhcp && /etc/init.d/dnsmasq restart && sleep 1",
        )
    print("Provisioned real HTTP/DNS dependencies in the disposable VM", flush=True)


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs)


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_http(url, timeout=45):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Test service did not become ready: {url}")


def spawn(args, state, label, env):
    with (state / f"{label}.log").open("w") as log:
        child = subprocess.Popen(
            args, cwd=ROOT, env=env, stdout=log, stderr=log, start_new_session=True
        )
    (state / f"{label}.pid").write_text(str(child.pid))


def start(state, images, python):
    if (ROOT / ".env").exists() or (ROOT / "backend/.env").exists():
        raise RuntimeError("The live test must run in a checkout without .env files")
    state.mkdir(mode=0o700)
    ssh_port, db_port, api_port = port(), port(), port()
    metadata = {
        "ssh_port": ssh_port,
        "db_port": db_port,
        "api_port": api_port,
        "project": "maxvpn-e2e-" + secrets.token_hex(5),
        "python": python,
    }
    with open(
        state / "state.json", "w", opener=lambda p, f: os.open(p, f, 0o600)
    ) as file:
        json.dump(metadata, file)
    lab = Lab(state / "lab")
    lab.start(images, ssh_port=ssh_port)
    print("Started isolated OpenWrt VMs; waiting for boot", flush=True)
    time.sleep(22)
    setup(lab)
    run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(state / "id_ed25519")]
    )
    lab.put(
        "router",
        "/etc/dropbear/authorized_keys",
        (state / "id_ed25519.pub").read_bytes(),
    )
    for command in (
        "uci set network.e2e=interface && uci set network.e2e.device=eth2 && uci set network.e2e.proto=static && uci set network.e2e.ipaddr=10.77.0.15 && uci set network.e2e.netmask=255.255.255.0 && uci commit network && /etc/init.d/network reload && sleep 2",
        "uci set firewall.e2e=zone && uci set firewall.e2e.name=e2e && uci set firewall.e2e.network=e2e && uci set firewall.e2e.input=ACCEPT && uci set firewall.e2e.output=ACCEPT && uci set firewall.e2e.forward=REJECT && uci commit firewall && /etc/init.d/firewall reload",
        "chmod 600 /etc/dropbear/authorized_keys && /etc/init.d/dropbear restart && /etc/init.d/maxvpn-appliance start && sleep 2",
    ):
        lab.command("router", command)
    # A separate WAN DNS server produces real forwarded answers in the router
    # query log, rather than synthetic log lines or local address overrides.
    lab.command(
        "wan",
        "uci set dhcp.@dnsmasq[0].noresolv=1 && uci add_list dhcp.@dnsmasq[0].address=/example.test/203.0.113.40 && uci commit dhcp && /etc/init.d/dnsmasq restart",
    )
    lab.command(
        "wan", "ip addr add 203.0.113.30/32 dev lo; ip addr add 203.0.113.40/32 dev lo"
    )
    lab.command(
        "router",
        "uci set dhcp.@dnsmasq[0].logqueries=1 && uci set dhcp.@dnsmasq[0].logfacility=/tmp/maxvpn-dns-events.log && uci set dhcp.@dnsmasq[0].noresolv=1 && uci add_list dhcp.@dnsmasq[0].rebind_domain=example.test && uci add_list dhcp.@dnsmasq[0].server=/example.test/198.18.0.1 && uci commit dhcp && /etc/init.d/dnsmasq restart && sleep 1",
    )
    services(state, python)


def services(state, python):
    metadata = json.loads((state / "state.json").read_text())
    ssh_port, db_port, api_port = (
        metadata[key] for key in ("ssh_port", "db_port", "api_port")
    )
    known = run(["ssh-keyscan", "-p", str(ssh_port), "127.0.0.1"]).stdout
    if not known:
        raise RuntimeError("No lab SSH host key")
    (state / "known_hosts").write_text(known)
    (state / "ssh_config").write_text(
        f"Host *\n  UserKnownHostsFile {state}/known_hosts\n  StrictHostKeyChecking yes\n  IdentitiesOnly yes\n"
    )
    (state / "bin").mkdir(exist_ok=True)
    wrapper = state / "bin/ssh"
    wrapper.write_text(f'#!/bin/sh\nexec /usr/bin/ssh -F {state}/ssh_config "$@"\n')
    wrapper.chmod(0o755)
    install_lab_dependencies(Lab(state / "lab"), state)
    project = metadata["project"]
    # This dedicated bridge publishes PostgreSQL only on host loopback. Docker
    # discards published ports on an internal network, which a host API needs.
    run(["docker", "network", "create", project])
    password = secrets.token_hex(24)
    run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            project,
            "--network",
            project,
            "-p",
            f"127.0.0.1:{db_port}:5432",
            "--tmpfs",
            "/var/lib/postgresql/data",
            "-e",
            "POSTGRES_DB=maxvpn_e2e",
            "-e",
            "POSTGRES_USER=maxvpn_e2e",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "postgres:17",
        ]
    )
    from cryptography.fernet import Fernet

    env = dict(os.environ)
    env.update(
        DATABASE_URL=f"postgresql+psycopg://maxvpn_e2e:{password}@127.0.0.1:{db_port}/maxvpn_e2e",
        SECRET_KEY=secrets.token_hex(32),
        VPN_CONFIG_ENCRYPTION_KEY=Fernet.generate_key().decode(),
        SSH_HOST="127.0.0.1",
        SSH_PORT=str(ssh_port),
        SSH_USERNAME="root",
        SSH_PRIVATE_KEY_PATH=str(state / "id_ed25519"),
        PYTHONPATH=f"{ROOT}:{ROOT}/backend",
        PYTHONDONTWRITEBYTECODE="1",
        MAXVPN_E2E_STATE=str(state),
        MAXVPN_LIVE_API_PORT=str(api_port),
        PATH=str(state / "bin") + ":" + os.environ["PATH"],
    )
    env["ALEMBIC_DATABASE_URL"] = env["DATABASE_URL"]
    for _ in range(40):
        result = subprocess.run(
            ["docker", "exec", project, "pg_isready", "-U", "maxvpn_e2e"],
            capture_output=True,
        )
        if result.returncode == 0:
            break
        time.sleep(0.5)
    run(
        [python, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
    )
    spawn(
        [
            python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(api_port),
        ],
        state,
        "api",
        env,
    )
    wait_http(f"http://127.0.0.1:{api_port}/health")
    spawn(["npm", "--prefix", "frontend", "run", "dev:live"], state, "frontend", env)
    wait_http("http://127.0.0.1:4179")
    print(
        f"Real API/PostgreSQL/SSH ready; frontend http://127.0.0.1:4179; state {state}",
        flush=True,
    )


def stop_services(state):
    for label in ("frontend", "api"):
        pidfile = state / f"{label}.pid"
        if pidfile.exists():
            pid = int(pidfile.read_text())
            environ = Path(f"/proc/{pid}/environ")
            if (
                environ.exists()
                and f"MAXVPN_E2E_STATE={state}".encode()
                in environ.read_bytes().split(b"\0")
            ):
                os.killpg(pid, signal.SIGTERM)
    metadata = json.loads((state / "state.json").read_text())
    if not metadata["project"].startswith("maxvpn-e2e-"):
        raise RuntimeError("Refusing to remove a non-test container")
    run(["docker", "rm", "-f", metadata["project"]])
    run(["docker", "network", "rm", metadata["project"]])


def stop(state):
    stop_services(state)
    Lab(state / "lab").stop()
    print("Stopped only the live test services; logs and overlays retained")


def api_environment(state):
    pid = int((state / "api.pid").read_text())
    environment = dict(
        item.split("=", 1)
        for item in Path(f"/proc/{pid}/environ").read_text().split("\0")
        if "=" in item
    )
    if environment.get("MAXVPN_E2E_STATE") != str(state):
        raise RuntimeError("The selected API is not this isolated test instance")
    return pid, environment


def restart_api(state):
    pid, environment = api_environment(state)
    os.killpg(pid, signal.SIGTERM)
    time.sleep(1)
    spawn(
        [
            json.loads((state / "state.json").read_text())["python"],
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            environment["MAXVPN_LIVE_API_PORT"],
        ],
        state,
        "api",
        environment,
    )
    wait_http("http://127.0.0.1:" + environment["MAXVPN_LIVE_API_PORT"] + "/health")
    print("Restarted only the isolated test API")


def reset_router(state):
    lab = Lab(state / "lab")
    lab.command(
        "router",
        "python3 /tmp/maxvpn-lab-seed.py && ipset flush MAXVPN_DIRECT",
        timeout=45,
    )
    print("Reset only the disposable lab routing fixture", flush=True)


def verify_browser_routing(state):
    lab = Lab(state / "lab")
    # Push/Apply has completed in the browser. Verify the kernel and real DNS.
    lab.command("router", "ipset test MAXVPN_DIRECT_STATIC 203.0.113.30")
    lab.command("client", "nslookup assets.example.test 192.168.77.1 >/dev/null")
    lab.command("router", "ipset test MAXVPN_DIRECT 203.0.113.40")
    verify(lab, "wan")
    verify(lab, "vless")
    for address in ("203.0.113.30", "203.0.113.40"):
        lab.command(
            "client", f"wget -T 3 -qO- http://{address}/lab.txt | grep -qx LAB_OK"
        )
    no_leaks(lab, "Browser-created CIDR and DNS exceptions pass alongside VLESS")
    lab.command("router", "/usr/bin/vpn-lan-off")
    print("Verified browser-created rules in kernel and real LAN traffic", flush=True)


def expired_token(state):
    import sys
    from jose import jwt

    _, environment = api_environment(state)
    algorithm = environment.get("ALGORITHM", "HS256")
    payload = jwt.decode(
        sys.stdin.read(), environment["SECRET_KEY"], algorithms=[algorithm]
    )
    payload["exp"] = 1
    # Only the browser test captures this disposable token; it is never logged.
    print(jwt.encode(payload, environment["SECRET_KEY"], algorithm=algorithm))


def verify_encrypted_profile(state):
    import sys
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    _, environment = api_environment(state)
    url = make_url(environment["DATABASE_URL"])
    if url.database != "maxvpn_e2e" or url.host != "127.0.0.1":
        raise RuntimeError("Only the disposable live database may be inspected")
    secret = sys.stdin.read().strip()
    if not secret:
        raise RuntimeError("Expected a disposable profile identity")
    engine = create_engine(url)
    with engine.connect() as connection:
        values = connection.scalars(
            text("SELECT encrypted_config FROM vless_profiles")
        ).all()
    engine.dispose()
    cipher = Fernet(environment["VPN_CONFIG_ENCRYPTION_KEY"].encode())
    if (
        not values
        or any(secret in value for value in values)
        or not any(
            secret in cipher.decrypt(value.encode()).decode() for value in values
        )
    ):
        raise RuntimeError("Profile encryption at rest was not verified")
    print("Verified encrypted profile storage in the real test database")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--images", default="/home/max-d/maxvpn-lab")
    parser.add_argument(
        "--python", default="/home/max-d/.venvs/maxvpn-backend/bin/python"
    )
    parser.add_argument(
        "action",
        choices=[
            "start",
            "services",
            "test",
            "stop",
            "expired-token",
            "restart-api",
            "verify-routing",
            "verify-encryption",
            "provision",
            "reset-services",
        ],
    )
    args = parser.parse_args()
    state = Path(args.state).resolve()
    if state.parent != Path("/tmp") or not state.name.startswith("maxvpn-live-e2e-"):
        raise RuntimeError(
            "Live tests require a private /tmp/maxvpn-live-e2e-* state directory"
        )
    if args.action == "start":
        start(state, args.images, args.python)
    elif args.action == "services":
        services(state, args.python)
    elif args.action == "stop":
        stop(state)
    elif args.action == "expired-token":
        expired_token(state)
    elif args.action == "restart-api":
        restart_api(state)
    elif args.action == "verify-routing":
        verify_browser_routing(state)
    elif args.action == "verify-encryption":
        verify_encrypted_profile(state)
    elif args.action == "provision":
        install_lab_dependencies(Lab(state / "lab"), state)
    elif args.action == "reset-services":
        stop_services(state)
        services(state, args.python)
    else:
        reset_router(state)
        env = dict(os.environ, MAXVPN_LIVE_STATE=str(state))
        subprocess.run(
            ["npm", "run", "test:live"], cwd=ROOT / "frontend", env=env, check=True
        )


if __name__ == "__main__":
    main()
