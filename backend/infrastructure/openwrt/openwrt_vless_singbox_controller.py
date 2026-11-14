from __future__ import annotations

import json
import re
import shlex
import time
import uuid
from collections.abc import Mapping
from typing import Any

from backend.infrastructure.openwrt.openwrt_lan_vpn_command_renderer import (
    OpenWrtLanVpnCommandRenderer,
)
from backend.ports.remote_command_executor import RemoteCommandExecutor


class OpenWrtVlessSingBoxController:
    """Manage sing-box separately from the existing AmneziaWG runtime."""

    EXPECTED_VERSION = "sing-box version 1.14.3"

    TEST_BINARY_PATH = "/root/sing-box-test"
    BINARY_PATH = "/usr/bin/sing-box"
    CONFIG_PATH = "/etc/maxvpn/sing-box-vless.json"
    PROFILE_STORE_PATH = "/etc/maxvpn/vless-profiles.json"
    SERVICE_PATH = OpenWrtLanVpnCommandRenderer.VLESS_SERVICE
    SERVICE_NAME = "maxvpn-sing-box"
    TUN_INTERFACE = "maxvpn0"

    SERVICE_SCRIPT = """#!/bin/sh /etc/rc.common
START=95
STOP=10
USE_PROCD=1

BIN="/usr/bin/sing-box"
CONFIG="/etc/maxvpn/sing-box-vless.json"

start_service() {
    [ -x "$BIN" ] || {
        echo "sing-box binary is missing" >&2
        return 1
    }

    [ -s "$CONFIG" ] || {
        echo "sing-box VLESS config is missing" >&2
        return 1
    }

    "$BIN" check -c "$CONFIG" || return 1

    procd_open_instance
    procd_set_param command "$BIN" run -c "$CONFIG"
    procd_set_param respawn 3600 5 5
    procd_set_param stdout 1
    procd_set_param stderr 1
    procd_close_instance
}
"""

    def __init__(
        self,
        executor: RemoteCommandExecutor,
    ) -> None:
        self._executor = executor

    def install_verified_binary(self) -> None:
        """Install the already-tested binary without overwriting an unknown build."""
        source = shlex.quote(self.TEST_BINARY_PATH)
        destination = shlex.quote(self.BINARY_PATH)
        expected = shlex.quote(self.EXPECTED_VERSION)

        script = f"""set -eu
src={source}
dst={destination}
expected={expected}

if [ -e "$dst" ]; then
    if [ -x "$dst" ]; then
        existing=$("$dst" version 2>/dev/null | sed -n '1p' || true)
        if [ "$existing" = "$expected" ]; then
            echo "sing-box binary already installed with expected version"
            exit 0
        fi
    fi
    echo "Refusing to overwrite an existing unverified sing-box binary" >&2
    exit 73
fi

[ -x "$src" ] || {{
    echo "Verified source binary is missing: $src" >&2
    exit 1
}}

source_version=$("$src" version | sed -n '1p')
[ "$source_version" = "$expected" ] || {{
    echo "Unexpected source binary version: $source_version" >&2
    exit 1
}}

tmp="${{dst}}.new.$$"
trap 'rm -f "$tmp"' EXIT
cp "$src" "$tmp"
chmod 755 "$tmp"

installed_version=$("$tmp" version | sed -n '1p')
[ "$installed_version" = "$expected" ] || {{
    echo "Copied binary version check failed" >&2
    exit 1
}}

mv "$tmp" "$dst"
"$dst" version | sed -n '1p'
"""
        self._run_checked(
            ["sh", "-c", script],
            action="Installing sing-box binary",
        )

    def install_service_script(self) -> None:
        """Install the procd service script, refusing unknown existing files."""
        destination = shlex.quote(self.SERVICE_PATH)

        script = f"""set -eu
dst={destination}
tmp="$(mktemp /etc/init.d/.maxvpn-sing-box.XXXXXX)"
trap 'rm -f "$tmp"' EXIT

cat > "$tmp"
chmod 755 "$tmp"
/bin/sh -n "$tmp"

if [ -e "$dst" ]; then
    if cmp -s "$dst" "$tmp"; then
        echo "sing-box service script already installed"
        exit 0
    fi
    echo "Refusing to overwrite an existing different service script: $dst" >&2
    exit 73
fi

mv "$tmp" "$dst"
echo "sing-box service script installed"
"""
        self._run_checked(
            ["sh", "-c", script],
            stdin=self.SERVICE_SCRIPT,
            action="Installing sing-box service",
        )

    def backup_config(self) -> str | None:
        """Create a private on-router backup of the current config, if present.

        The configuration (which contains credentials) never leaves the router;
        only the generated backup path is returned to the backend.
        """
        suffix = uuid.uuid4().hex
        backup_path = f"{self.CONFIG_PATH}.maxvpn-backup-{suffix}"
        destination = shlex.quote(self.CONFIG_PATH)
        backup = shlex.quote(backup_path)
        script = f"""set -eu
dst={destination}
bak={backup}
if [ -f "$dst" ]; then
    cp -p "$dst" "$bak"
    chmod 600 "$bak"
    printf '%s\n' "$bak"
fi
"""
        result = self._executor.run(["sh", "-c", script])
        self._check_result(result, "Backing up the current sing-box config")
        value = (result.stdout or "").strip()
        if not value:
            return None
        self._validate_backup_path(value)
        return value

    def restore_config(self, backup_path: str | None) -> None:
        """Restore the previous config without changing LAN routes."""
        destination = shlex.quote(self.CONFIG_PATH)
        if backup_path is None:
            script = (
                f"set -eu\nrm -f {destination}\n"
                "echo 'Previous config was absent; failed config removed'\n"
            )
            self._run_checked(
                ["sh", "-c", script],
                action="Removing failed VLESS config",
            )
            return

        self._validate_backup_path(backup_path)
        backup = shlex.quote(backup_path)
        binary = shlex.quote(self.BINARY_PATH)
        script = f"""set -eu
dst={destination}
bak={backup}
bin={binary}
dir="${{dst%/*}}"
[ -f "$bak" ] || {{ echo "VLESS config backup is missing" >&2; exit 1; }}
[ -x "$bin" ] || {{ echo "sing-box binary is missing during rollback" >&2; exit 1; }}
tmp="$(mktemp "$dir/.sing-box-vless.restore.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
cp -p "$bak" "$tmp"
"$bin" check -c "$tmp"
mv -f "$tmp" "$dst"
chmod 600 "$dst"
rm -f "$bak"
echo 'Previous VLESS config restored and validated'
"""
        self._run_checked(
            ["sh", "-c", script],
            action="Restoring previous VLESS config",
        )

    @classmethod
    def _validate_backup_path(cls, backup_path: str) -> None:
        expected_prefix = f"{cls.CONFIG_PATH}.maxvpn-backup-"
        pattern = re.escape(expected_prefix) + r"[a-f0-9]{32}"
        if not re.fullmatch(pattern, backup_path):
            raise ValueError("Invalid sing-box config backup path")

    def discard_config_backup(self, backup_path: str | None) -> None:
        """Remove a completed transaction's backup; never accepts arbitrary paths."""
        if backup_path is None:
            return
        self._validate_backup_path(backup_path)
        backup = shlex.quote(backup_path)
        # Backup cleanup is best-effort; successful startup must not be reported
        # as failed merely because a redundant private backup remains on disk.
        self._executor.run(["sh", "-c", f"rm -f {backup} 2>/dev/null || true\n"])

    def install_config(self, config: Mapping[str, Any]) -> None:
        """Validate the required TUN design, then atomically write its config."""
        self._validate_config(config)

        payload = (
            json.dumps(
                config,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )

        config_path = shlex.quote(self.CONFIG_PATH)
        binary_path = shlex.quote(self.BINARY_PATH)

        script = f"""set -eu
dst={config_path}
bin={binary_path}
dir="${{dst%/*}}"

[ -x "$bin" ] || {{
    echo "sing-box binary is not installed" >&2
    exit 1
}}

mkdir -p "$dir"
tmp="$(mktemp "$dir/.sing-box-vless.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

cat > "$tmp"
chmod 600 "$tmp"
"$bin" check -c "$tmp"
mv -f "$tmp" "$dst"
chmod 600 "$dst"

echo "sing-box VLESS config validated and installed"
"""
        self._run_checked(
            ["sh", "-c", script],
            stdin=payload,
            action="Installing VLESS config",
        )

    def start(self) -> None:
        """Start sing-box and enable autostart, without changing LAN routes."""
        self._run_checked(
            [self.SERVICE_PATH, "start"],
            action="Starting sing-box",
        )

        if not self.status()["running"]:
            self._executor.run([self.SERVICE_PATH, "stop"])
            raise RuntimeError(
                "sing-box service start returned success but no running "
                "procd instance was reported"
            )

        self._run_checked(
            [self.SERVICE_PATH, "enable"],
            action="Enabling sing-box autostart",
        )

    def stop(self) -> None:
        """Stop sing-box without editing VPN mode or routing tables."""
        self._run_checked(
            [self.SERVICE_PATH, "stop"],
            action="Stopping sing-box",
        )

        if self.status()["running"]:
            raise RuntimeError("sing-box still reports a running procd instance")

    def stop_with_lan_fallback(self) -> bool:
        """Switch active VLESS LAN to WAN and stop under the router runtime lock."""
        result = self._executor.run(
            ["sh", "-s"],
            stdin=OpenWrtLanVpnCommandRenderer().render_vless_stop(),
        )
        self._check_result(result, "Stopping sing-box with LAN fallback")
        previous_mode = result.stdout.strip()
        if previous_mode not in {"vpn", "wan", "vless"}:
            raise RuntimeError("OpenWrt returned an invalid previous LAN mode")
        return previous_mode == "vless"

    def disable_autostart(self) -> None:
        """Disable the sing-box service at boot, without touching routing."""
        self._run_checked(
            [self.SERVICE_PATH, "disable"],
            action="Disabling sing-box autostart",
        )

    def _run_read_only_command_with_ssh_retry(self, command: list[str]) -> Any:
        """Retry an idempotent remote read once on an SSH transport failure."""
        result = self._executor.run(command)
        transient_markers = (
            "connection closed by",
            "connection reset by peer",
            "connection timed out",
            "broken pipe",
        )
        detail = str(getattr(result, "stderr", "") or "").lower()
        if getattr(result, "returncode", 1) != 0 and any(
            marker in detail for marker in transient_markers
        ):
            time.sleep(0.2)
            result = self._executor.run(command)
        return result

    def status(self) -> dict[str, bool]:
        """Read procd status. This does not start or stop the service."""
        command = [
            "ubus",
            "call",
            "service",
            "list",
            json.dumps(
                {"name": self.SERVICE_NAME, "verbose": True},
                separators=(",", ":"),
            ),
        ]
        result = self._run_read_only_command_with_ssh_retry(command)
        self._check_result(result, "Reading sing-box service status")

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenWrt returned invalid procd status JSON") from exc

        service = payload.get(self.SERVICE_NAME)
        if not isinstance(service, dict):
            # procd/ubus may omit a stopped service entirely. Detect the installed
            # runtime from its files instead of treating an empty ubus object as
            # proof that sing-box is not installed.
            install_check = self._run_read_only_command_with_ssh_retry(
                [
                    "sh",
                    "-c",
                    "test -x /usr/bin/sing-box && "
                    "test -x /etc/init.d/maxvpn-sing-box && "
                    "test -f /etc/maxvpn/sing-box-vless.json",
                ]
            )
            if install_check.returncode not in (0, 1):
                self._check_result(install_check, "Checking installed sing-box files")
            return {
                "installed": install_check.returncode == 0,
                "running": False,
            }

        instances = service.get("instances")
        running = isinstance(instances, dict) and any(
            isinstance(instance, dict) and instance.get("running") is True
            for instance in instances.values()
        )
        return {"installed": True, "running": bool(running)}

    @staticmethod
    def _validate_proxy_tag(tag: str) -> None:
        import re

        if not re.fullmatch(r"(?:vless-auto|vless-profile-[1-9][0-9]*)", tag):
            raise ValueError("Invalid VLESS proxy tag")

    def selected_outbound(self) -> str | None:
        """Return the selected member of the local selector via loopback Clash API."""
        result = self._executor.run(
            [
                "sh",
                "-c",
                "curl -fsS --max-time 3 http://127.0.0.1:9090/proxies/vless-out",
            ]
        )
        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError("Unable to query the local sing-box Clash API")
        try:
            payload = json.loads(getattr(result, "stdout", "") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("sing-box Clash API returned invalid JSON") from exc
        selected = payload.get("now")
        if not isinstance(selected, str) or not selected:
            raise RuntimeError("sing-box selector did not report its selected outbound")
        return selected

    def read_appliance_vless_store(self) -> dict[str, Any]:
        """Read the private appliance profile store over SSH for an explicit sync.

        Credentials remain inside the authenticated backend process and are never
        returned by the sync-status API. This method is read-only.
        """
        command = ["cat", self.PROFILE_STORE_PATH]
        result = self._executor.run(command)

        # Reading the profile store is idempotent: retry once only for
        # recognized SSH transport failures.
        transient_markers = (
            "connection closed by",
            "connection reset by peer",
            "connection timed out",
            "broken pipe",
        )
        detail = str(getattr(result, "stderr", "") or "").lower()
        if getattr(result, "returncode", 1) != 0 and any(
            marker in detail for marker in transient_markers
        ):
            time.sleep(0.2)
            result = self._executor.run(command)

        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError("Unable to read VLESS profiles from maxvpn.lan")
        try:
            payload = json.loads(getattr(result, "stdout", "") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Appliance VLESS profile store contains invalid JSON"
            ) from exc
        profiles = payload.get("profiles") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or not isinstance(profiles, list)
            or len(profiles) > 50
        ):
            raise RuntimeError(
                "Appliance VLESS profile store has an unsupported format"
            )
        return payload

    def set_wan_fallback_enabled(self, enabled: bool) -> dict[str, Any]:
        """Update the appliance's WAN fallback policy through its loopback API."""
        if not isinstance(enabled, bool):
            raise ValueError("WAN fallback setting must be a boolean")
        payload = json.dumps(
            {"wan_fallback_enabled": enabled},
            separators=(",", ":"),
        )
        script = (
            "curl -fsS --max-time 8 -X POST "
            "-H 'Content-Type: application/json' "
            f"--data-binary {shlex.quote(payload)} "
            "http://127.0.0.1:8787/api/appliance/v1/vless/settings"
        )
        result = self._executor.run(["sh", "-c", script])
        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError("Unable to update the Kill Switch setting on maxvpn.lan")
        try:
            response = json.loads(getattr(result, "stdout", "") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("maxvpn.lan returned invalid Kill Switch state") from exc
        settings = response.get("settings") if isinstance(response, dict) else None
        if (
            not isinstance(settings, dict)
            or settings.get("wan_fallback_enabled") is not enabled
        ):
            raise RuntimeError("maxvpn.lan did not confirm the Kill Switch setting")
        return {
            "kill_switch_enabled": not enabled,
            "wan_fallback_active": response.get("wan_fallback_active") is True,
        }

    def _appliance_profile_endpoint(
        self, outbound_tag: str | None
    ) -> tuple[str | None, int | None]:
        """Resolve a router-side outbound tag to its endpoint without returning
        secrets."""
        if not isinstance(outbound_tag, str):
            return None, None
        match = re.fullmatch(r"vless-profile-([1-9][0-9]*)", outbound_tag)
        if not match:
            return None, None
        try:
            store = self.read_appliance_vless_store()
        except RuntimeError:
            return None, None
        profile_id = int(match.group(1))
        for profile in store.get("profiles", []):
            if not isinstance(profile, dict):
                continue
            try:
                same_id = int(profile.get("id", -1)) == profile_id
                port = int(profile.get("port"))
            except (TypeError, ValueError):
                continue
            address = profile.get("address")
            if same_id and isinstance(address, str) and address and 1 <= port <= 65535:
                return address, port
        return None, None

    def runtime_server_info(self) -> dict[str, Any]:
        """Report the active outbound, including the live legacy single-server config.

        Never infer that the first saved profile is active. Prefer the local Clash
        API; if it is not present, inspect only the active route's outbound in the
        installed config and return its server address/port without credentials.
        """
        import json
        import re
        import shlex

        try:
            selected = self.selected_outbound()
        except RuntimeError:
            selected = None
        else:
            if selected == "vless-auto":
                try:
                    active = self.active_outbound(selected)
                except RuntimeError:
                    active = None
                address, port = self._appliance_profile_endpoint(active)
                return {
                    "selected_outbound": selected,
                    "active_outbound": active,
                    "active_server_address": address,
                    "active_server_port": port,
                    "selection_mode": "auto",
                    "runtime_config_mode": "multi_profile",
                }
            if isinstance(selected, str) and re.fullmatch(
                r"vless-profile-[1-9][0-9]*", selected
            ):
                address, port = self._appliance_profile_endpoint(selected)
                return {
                    "selected_outbound": selected,
                    "active_outbound": selected,
                    "active_server_address": address,
                    "active_server_port": port,
                    "selection_mode": "manual",
                    "runtime_config_mode": "multi_profile",
                }
            return {
                "selected_outbound": selected,
                "active_outbound": None,
                "active_server_address": None,
                "active_server_port": None,
                "selection_mode": "unknown",
                "runtime_config_mode": "unknown",
            }

        command = "cat " + shlex.quote(self.CONFIG_PATH)
        result = self._executor.run(["sh", "-c", command])
        if getattr(result, "returncode", 1) != 0:
            return {
                "selected_outbound": None,
                "active_outbound": None,
                "active_server_address": None,
                "active_server_port": None,
                "selection_mode": "unknown",
                "runtime_config_mode": "unknown",
            }
        try:
            config = json.loads(getattr(result, "stdout", "") or "{}")
        except json.JSONDecodeError:
            return {
                "selected_outbound": None,
                "active_outbound": None,
                "active_server_address": None,
                "active_server_port": None,
                "selection_mode": "unknown",
                "runtime_config_mode": "unknown",
            }

        outbounds = config.get("outbounds", []) if isinstance(config, dict) else []
        route = config.get("route", {}) if isinstance(config, dict) else {}
        final_tag = route.get("final") if isinstance(route, dict) else None
        active = (
            next(
                (
                    item
                    for item in outbounds
                    if isinstance(item, dict) and item.get("tag") == final_tag
                ),
                None,
            )
            if isinstance(outbounds, list)
            else None
        )

        if isinstance(active, dict) and active.get("type") == "vless":
            address = active.get("server")
            port = active.get("server_port")
            return {
                "selected_outbound": None,
                "active_outbound": (
                    active.get("tag")
                    if isinstance(active.get("tag"), str)
                    and re.fullmatch(r"vless-profile-[1-9][0-9]*", active["tag"])
                    else None
                ),
                "active_server_address": address if isinstance(address, str) else None,
                "active_server_port": (
                    port
                    if isinstance(port, int) and not isinstance(port, bool)
                    else None
                ),
                "selection_mode": "legacy",
                "runtime_config_mode": "single_profile",
            }

        is_multi = isinstance(outbounds, list) and any(
            isinstance(item, dict)
            and item.get("tag") == "vless-auto"
            and item.get("type") == "urltest"
            for item in outbounds
        )
        return {
            "selected_outbound": None,
            "active_outbound": None,
            "active_server_address": None,
            "active_server_port": None,
            "selection_mode": "unknown",
            "runtime_config_mode": "multi_profile" if is_multi else "unknown",
        }

    def active_outbound(self, selected: str | None = None) -> str | None:
        """Return the real active VLESS member, including a URLTest group's
        current member."""
        import re

        if selected is None:
            selected = self.selected_outbound()
        if selected != "vless-auto":
            return (
                selected
                if re.fullmatch(r"vless-profile-[1-9][0-9]*", selected)
                else None
            )

        result = self._executor.run(
            [
                "sh",
                "-c",
                "curl -fsS --max-time 3 http://127.0.0.1:9090/proxies/vless-auto",
            ]
        )
        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError(
                "Unable to query the active member of the VLESS URLTest group"
            )
        try:
            import json

            payload = json.loads(getattr(result, "stdout", "") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("sing-box URLTest API returned invalid JSON") from exc
        active = payload.get("now")
        if isinstance(active, str) and re.fullmatch(
            r"vless-profile-[1-9][0-9]*", active
        ):
            return active
        # sing-box may not have completed its first URLTest yet.
        return None

    def select_outbound(self, tag: str) -> None:
        """Select a manual VLESS profile or return to automatic URLTest selection."""
        self._validate_proxy_tag(tag)
        import shlex

        payload = json.dumps({"name": tag}, separators=(",", ":"))
        script = (
            "curl -fsS --max-time 4 -X PUT "
            "-H 'Content-Type: application/json' "
            f"--data-binary {shlex.quote(payload)} "
            "http://127.0.0.1:9090/proxies/vless-out >/dev/null"
        )
        result = self._executor.run(["sh", "-c", script])
        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError("sing-box refused the outbound selection")
        if self.selected_outbound() != tag:
            raise RuntimeError("sing-box outbound selection verification failed")

    def selection_history(self) -> dict[str, Any]:
        """Read the appliance's persisted VLESS selection journal without
        probing servers."""
        command = [
            "sh",
            "-c",
            "curl -fsS --max-time 5 "
            "http://127.0.0.1:8787/api/appliance/v1/vless/selection-history",
        ]
        result = self._executor.run(command)

        # The journal read is idempotent; retry once only for SSH transport faults.
        transient_markers = (
            "connection closed by",
            "connection reset by peer",
            "connection timed out",
            "broken pipe",
        )
        detail = str(getattr(result, "stderr", "") or "").lower()
        if getattr(result, "returncode", 1) != 0 and any(
            marker in detail for marker in transient_markers
        ):
            time.sleep(0.2)
            result = self._executor.run(command)

        if getattr(result, "returncode", 1) != 0:
            raise RuntimeError(
                "Unable to read VLESS selection history from the appliance"
            )
        try:
            payload = json.loads(getattr(result, "stdout", "") or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "Appliance returned invalid VLESS selection history JSON"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise RuntimeError(
                "Appliance returned an invalid VLESS selection history payload"
            )
        return payload

    def test_outbound_delays(self, tags: list[str]) -> dict[str, int | None]:
        """Measure HTTPS response latency via each outbound; failures return None."""
        from concurrent.futures import ThreadPoolExecutor

        for tag in tags:
            self._validate_proxy_tag(tag)
        if not tags:
            return {}

        def test_one(tag: str) -> tuple[str, int | None]:
            script = (
                "curl -fsS --max-time 7 --get "
                "--data-urlencode 'url=https://cp.cloudflare.com/generate_204' "
                "--data-urlencode 'timeout=5000' "
                f"'http://127.0.0.1:9090/proxies/{tag}/delay'"
            )
            try:
                result = self._executor.run(["sh", "-c", script])
                if getattr(result, "returncode", 1) != 0:
                    return tag, None
                payload = json.loads(getattr(result, "stdout", "") or "{}")
                delay = payload.get("delay")
                if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
                    return tag, None
                return tag, delay
            except (RuntimeError, ValueError, TypeError, json.JSONDecodeError):
                return tag, None

        # Bound parallel requests so a 50-profile test does not overload the router.
        with ThreadPoolExecutor(max_workers=5) as pool:
            return dict(pool.map(test_one, tags))

    @classmethod
    def _validate_config(cls, config: Mapping[str, Any]) -> None:
        if not isinstance(config, Mapping):
            raise ValueError("sing-box config must be an object")

        inbounds = config.get("inbounds")
        if not isinstance(inbounds, list):
            raise ValueError("sing-box config must contain an inbounds list")

        tun = next(
            (
                item
                for item in inbounds
                if isinstance(item, Mapping) and item.get("type") == "tun"
            ),
            None,
        )
        if tun is None:
            raise ValueError("VLESS config must contain a TUN inbound")
        if tun.get("interface_name") != cls.TUN_INTERFACE:
            raise ValueError(f"TUN interface must be {cls.TUN_INTERFACE!r}")
        if tun.get("auto_route") is not False:
            raise ValueError(
                "sing-box auto_route must be false; MaxVPN manages routes separately"
            )

        outbounds = config.get("outbounds")
        if not isinstance(outbounds, list):
            raise ValueError("config must contain an outbounds list")
        primary = next(
            (
                item
                for item in outbounds
                if isinstance(item, Mapping) and item.get("tag") == "vless-out"
            ),
            None,
        )
        if primary is None or primary.get("type") not in ("vless", "selector"):
            raise ValueError(
                "config must contain the vless-out VLESS outbound or selector"
            )
        if primary.get("type") == "selector":
            automatic = next(
                (
                    item
                    for item in outbounds
                    if isinstance(item, Mapping) and item.get("tag") == "vless-auto"
                ),
                None,
            )
            if not isinstance(automatic, Mapping) or automatic.get("type") != "urltest":
                raise ValueError(
                    "multi-profile config must contain the vless-auto URLTest group"
                )
            members = automatic.get("outbounds")
            if not isinstance(members, list) or not members or len(members) > 50:
                raise ValueError(
                    "vless-auto must contain between 1 and 50 server outbounds"
                )
            member_tags = set(members)
            available = {
                item.get("tag")
                for item in outbounds
                if isinstance(item, Mapping) and item.get("type") == "vless"
            }
            if not member_tags.issubset(available):
                raise ValueError("vless-auto references a missing VLESS outbound")

        route = config.get("route")
        if not isinstance(route, Mapping):
            raise ValueError("config must contain a route object")
        if route.get("final") != "vless-out":
            raise ValueError("default route must use vless-out")
        if route.get("auto_detect_interface") is not True:
            raise ValueError(
                "route.auto_detect_interface must be true to prevent routing loops"
            )

    @staticmethod
    def _check_result(result, action: str) -> None:
        if result.returncode != 0:
            detail = result.stderr or result.stdout or "no remote error detail"
            raise RuntimeError(
                f"{action} failed with exit code {result.returncode}: {detail}"
            )

    def _run_checked(
        self,
        command: list[str],
        *,
        action: str,
        stdin: str | None = None,
    ) -> None:
        result = self._executor.run(command, stdin=stdin)
        self._check_result(result, action)
