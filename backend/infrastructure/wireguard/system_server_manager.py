from __future__ import annotations

import subprocess
import time
from pathlib import Path

from backend.ports.wireguard_server_manager import WireGuardServerManager


class SystemWireGuardServerManager(WireGuardServerManager):
    """
    Manages a WireGuard server interface using system commands.

    Supports:
    - kernel WireGuard via `ip link add ... type wireguard`
    - userspace WireGuard via `wireguard-go`
    """

    def __init__(
        self,
        interface_name: str,
        wg_binary: str = "wg",
        ip_binary: str = "ip",
        wireguard_go_binary: str = "wireguard-go",
        backend: str = "kernel",
    ) -> None:
        if backend not in {"kernel", "userspace"}:
            raise ValueError(
                f"Unsupported WireGuard backend: {backend!r}. "
                "Expected 'kernel' or 'userspace'."
            )

        self._interface_name = interface_name
        self._wg_binary = wg_binary
        self._ip_binary = ip_binary
        self._wireguard_go_binary = wireguard_go_binary
        self._backend = backend
        self._userspace_process: subprocess.Popen[bytes] | None = None

    def generate_private_key(self) -> str:
        result = subprocess.run(
            [
                self._wg_binary,
                "genkey",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        private_key = result.stdout.strip()

        if not private_key:
            raise RuntimeError("WireGuard failed to generate a private key.")

        return private_key

    def interface_exists(self) -> bool:
        result = subprocess.run(
            [
                self._ip_binary,
                "link",
                "show",
                "dev",
                self._interface_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        return result.returncode == 0

    def ensure_interface(self) -> None:
        if self.interface_exists():
            return

        if self._backend == "kernel":
            self._ensure_kernel_interface()
            return

        self._ensure_userspace_interface()

    def _ensure_kernel_interface(self) -> None:
        subprocess.run(
            [
                self._ip_binary,
                "link",
                "add",
                self._interface_name,
                "type",
                "wireguard",
            ],
            check=True,
        )

    def _ensure_userspace_interface(self) -> None:
        process = subprocess.Popen(
            [
                self._wireguard_go_binary,
                "-f",
                self._interface_name,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        self._userspace_process = process

        deadline = time.monotonic() + 5.0

        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    "wireguard-go exited before the interface became ready. "
                    f"Exit code: {process.returncode}."
                )

            if self.interface_exists():
                ready = subprocess.run(
                    [
                        self._wg_binary,
                        "show",
                        self._interface_name,
                        "listen-port",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if ready.returncode == 0:
                    return

            time.sleep(0.05)

        process.terminate()

        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()

        raise RuntimeError(
            "Timed out waiting for userspace WireGuard "
            f"interface '{self._interface_name}' to become ready."
        )

    def configure(
        self,
        private_key: str,
        listen_port: int,
    ) -> None:
        key_path = Path(f"/tmp/{self._interface_name}.privatekey")

        try:
            key_path.write_text(
                private_key,
                encoding="utf-8",
            )
            key_path.chmod(0o600)

            subprocess.run(
                [
                    self._wg_binary,
                    "set",
                    self._interface_name,
                    "private-key",
                    str(key_path),
                    "listen-port",
                    str(listen_port),
                ],
                check=True,
            )
        finally:
            key_path.unlink(missing_ok=True)

    def configure_address(self, address: str) -> None:
        subprocess.run(
            [
                self._ip_binary,
                "address",
                "replace",
                address,
                "dev",
                self._interface_name,
            ],
            check=True,
        )

    def set_up(self) -> None:
        subprocess.run(
            [
                self._ip_binary,
                "link",
                "set",
                "dev",
                self._interface_name,
                "up",
            ],
            check=True,
        )

    def set_down(self) -> None:
        subprocess.run(
            [
                self._ip_binary,
                "link",
                "set",
                "dev",
                self._interface_name,
                "down",
            ],
            check=True,
        )

    def is_up(self) -> bool:
        result = subprocess.run(
            [
                self._ip_binary,
                "link",
                "show",
                "dev",
                self._interface_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            return False

        return "UP" in result.stdout

    def remove_interface(self) -> None:
        if not self.interface_exists():
            return

        subprocess.run(
            [
                self._ip_binary,
                "link",
                "delete",
                "dev",
                self._interface_name,
            ],
            check=True,
        )

    def get_public_key(self) -> str:
        result = subprocess.run(
            [
                self._wg_binary,
                "show",
                self._interface_name,
                "public-key",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        public_key = result.stdout.strip()

        if not public_key:
            raise RuntimeError(
                f"WireGuard interface '{self._interface_name}' has no public key."
            )

        return public_key
