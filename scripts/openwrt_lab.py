"""Isolated QEMU lab: copy-on-write disks, loopback sockets, serial-only control.

No bridged/TAP/user networking, host forwarding or physical router connections.
"""

import argparse
import base64
import hashlib
import gzip
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import threading
import time
import uuid


class Lab:
    def __init__(self, state):
        self.state = Path(state).resolve()

    def start(self, images, resume=False):
        if resume:
            for pidfile in self.state.glob("*.pid"):
                if Path(f"/proc/{int(pidfile.read_text())}/cmdline").exists():
                    raise RuntimeError("Stop all lab VMs before resuming")
            previous = uuid.uuid4().hex[:8]
            for name in ("wan-wire.pcap", "evidence.jsonl", "capture-start"):
                artifact = self.state / name
                if artifact.exists():
                    artifact.rename(self.state / f"prior-{previous}-{name}")
        else:
            self.state.mkdir(mode=0o700)
        # QEMU's TCP socket networks bind exclusively to loopback.
        ports = []
        for _ in range(2):
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                ports.append(sock.getsockname()[1])
        for node in ("router", "client", "wan"):
            disk = self.state / f"{node}.qcow2"
            if not resume:
                base = (Path(images) / f"{node}.qcow2").resolve(strict=True)
                subprocess.run(
                    [
                        "qemu-img",
                        "create",
                        "-f",
                        "qcow2",
                        "-F",
                        "qcow2",
                        "-b",
                        str(base),
                        str(disk),
                    ],
                    check=True,
                    capture_output=True,
                )
            args = [
                "qemu-system-x86_64",
                "-name",
                f"maxvpn-pr2-{node}",
                "-accel",
                "kvm",
                "-m",
                "256",
                "-smp",
                "1",
                "-display",
                "none",
                "-drive",
                f"file={disk},format=qcow2,if=virtio",
                "-serial",
                f"unix:{self.state}/{node}.serial,server=on,wait=off",
                "-monitor",
                "none",
                "-pidfile",
                str(self.state / f"{node}.pid"),
                "-daemonize",
            ]
            links = (
                [("lan", "listen", ports[0]), ("wan", "listen", ports[1])]
                if node == "router"
                else [(node, "connect", ports[0 if node == "client" else 1])]
            )
            for index, (name, direction, port) in enumerate(links):
                args += [
                    "-netdev",
                    f"socket,id={name},{direction}=127.0.0.1:{port}",
                    "-device",
                    f"virtio-net-pci,netdev={name},mac=52:54:00:12:{('router', 'client', 'wan').index(node) + 1:02x}:{index + 1:02x}",
                ]
                if node == "router" and name == "wan":
                    args += [
                        "-object",
                        f"filter-dump,id=wan-capture,netdev=wan,file={self.state}/wan-wire.pcap",
                    ]
            subprocess.run(args, check=True, capture_output=True)
        print(f"Started isolated lab at {self.state}")

    def command(self, node, command, timeout=30):
        token = uuid.uuid4().hex
        marker = f"__LAB_{token}:"
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(0.2)
            sock.connect(str(self.state / f"{node}.serial"))
            sock.sendall(b"\x03\n")
            time.sleep(0.2)
            # Drain boot messages before sending the actual command.
            try:
                while sock.recv(65536):
                    pass
            except socket.timeout:
                pass
            payload = (
                f"printf '\\n%s%s\\n' '__LAB_START_' '{token}'\n{command}\nlab_status=$?; "
                f"printf '\\n%s%s:%s\\n' '__LAB_' '{token}' \"$lab_status\"\n"
            )
            chunks = []
            finished = threading.Event()

            def receive():
                while not finished.is_set():
                    try:
                        chunk = sock.recv(65536)
                        if not chunk:
                            return
                        chunks.append(chunk)
                    except socket.timeout:
                        continue

            receiver = threading.Thread(target=receive, daemon=True)
            receiver.start()
            encoded_payload = payload.encode()
            for offset in range(0, len(encoded_payload), 128):
                sock.sendall(encoded_payload[offset : offset + 128])
                time.sleep(0.02)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(0.05)
                decoded = b"".join(chunks).decode(errors="replace").replace("\r", "")
                match = re.search(re.escape(marker) + r"(\d+)\n", decoded)
                if match:
                    finished.set()
                    receiver.join(timeout=1)
                    start = decoded.find(f"__LAB_START_{token}\n")
                    body = decoded[
                        start + len(f"__LAB_START_{token}\n") : match.start()
                    ].strip()
                    if match.group(1) != "0":
                        raise RuntimeError(
                            f"{node} command failed ({match.group(1)}): {body}"
                        )
                    return body
            finished.set()
            receiver.join(timeout=1)
        raise TimeoutError(f"{node}: no completion marker within {timeout}s")

    def put(self, node, path, content):
        if len(content) < 1000:
            output = self.command(
                node,
                f"printf '%s' {shlex.quote(content.decode())} > {shlex.quote(path)}; sha256sum {shlex.quote(path)}",
            )
            if hashlib.sha256(content).hexdigest() not in output:
                raise RuntimeError(f"Transfer checksum mismatch: {node}:{path}")
            return
        # Short heredoc lines avoid the serial console's canonical line limit.
        encoded = base64.b64encode(gzip.compress(content)).decode()
        lines = "\n".join(encoded[i : i + 240] for i in range(0, len(encoded), 240))
        output = self.command(
            node,
            f"python3 -c \"import base64,gzip,sys;open('{path}','wb').write(gzip.decompress(base64.b64decode(sys.stdin.read())))\" <<'__PAYLOAD__'\n{lines}\n__PAYLOAD__\nsha256sum {path}",
            timeout=45,
        )
        if hashlib.sha256(content).hexdigest() not in output:
            raise RuntimeError(f"Transfer checksum mismatch: {node}:{path}")

    def stop(self):
        for node in ("client", "wan", "router"):
            pidfile = self.state / f"{node}.pid"
            if not pidfile.exists():
                continue
            pid = int(pidfile.read_text())
            proc = Path(f"/proc/{pid}/cmdline")
            if proc.exists() and str(self.state).encode() in proc.read_bytes():
                os.kill(pid, signal.SIGTERM)
        print("Stopped lab VMs; overlay disks and evidence retained")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("start")
    start.add_argument("--images", required=True)
    start.add_argument("--resume", action="store_true")
    command = sub.add_parser("exec")
    command.add_argument("node", choices=["router", "client", "wan"])
    command.add_argument("command")
    sub.add_parser("stop")
    args = parser.parse_args()
    lab = Lab(args.state)
    if args.action == "start":
        lab.start(args.images, resume=args.resume)
    elif args.action == "exec":
        print(lab.command(args.node, args.command))
    else:
        lab.stop()


if __name__ == "__main__":
    main()
