#!/usr/bin/env python3
"""Local VLESS + REALITY management for the MaxVPN OpenWrt appliance.

Python 3.9 compatible. Secrets are stored only in a root-owned file with mode 0600.
The module does not change routing unless set_mode() is explicitly called.
"""

import copy
import json
import datetime as _selection_datetime
import uuid
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path("/opt/maxvpn-appliance")
DATA = ROOT / "data"
BACKUP_DIR = DATA / "vless-backups"
DELAY_HISTORY_FILE = DATA / "vless-delay-history.json"
PROFILE_FILE = Path("/etc/maxvpn/vless-profiles.json")
CONFIG_FILE = Path("/etc/maxvpn/sing-box-vless.json")
SING_BOX = Path("/usr/bin/sing-box")
SERVICE = Path("/etc/init.d/maxvpn-sing-box")
VLESS_STOP_HELPER = "/usr/bin/vpn-lan-vless-stop"
MODE_FILE = Path("/etc/maxvpn/runtime-mode")
MAX_PROFILES = 50
URLTEST_URL = "https://cp.cloudflare.com/generate_204"
ALLOWED_INTERVALS = ("30s", "1m", "2m", "3m", "5m", "10m")
WAN_FALLBACK_FAILURE_THRESHOLD = 2
WAN_FALLBACK_RECOVERY_THRESHOLD = 2
LOCK = threading.RLock()


def _utc_now():
    """Return an aware UTC timestamp; kept separate for deterministic tests."""
    return datetime.now(timezone.utc)


def _timestamp_iso(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _timestamp_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return (
        parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None
        else parsed.astimezone(timezone.utc)
    )


def _serialized(method):
    """Serialize profile/config mutations handled by ThreadingHTTPServer."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with LOCK:
            return method(self, *args, **kwargs)

    return wrapper


class VlessControlError(Exception):
    """Safe, user-facing error raised by local VLESS management."""


def _run(args, timeout=12, check=False, input_text=None):
    try:
        return subprocess.run(
            [str(x) for x in args],
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise VlessControlError(
            "Команда управления VLESS превысила время ожидания."
        ) from exc
    except OSError as exc:
        raise VlessControlError(
            "Не удалось выполнить системную команду управления VLESS."
        ) from exc


def _read_json_file(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _normalize_profile(profile):
    if not isinstance(profile, dict):
        raise ValueError("Профиль должен быть объектом JSON.")
    address = str(profile.get("address") or "").strip()
    if not address or len(address) > 253 or any(ch.isspace() for ch in address):
        raise ValueError("Некорректный адрес VLESS-сервера.")
    try:
        port = int(profile.get("port"))
    except (TypeError, ValueError):
        raise ValueError("Порт VLESS-сервера должен быть числом.")
    if not 1 <= port <= 65535:
        raise ValueError("Порт VLESS-сервера вне диапазона 1–65535.")
    uuid = str(profile.get("uuid") or "").strip()
    if not re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}",
        uuid,
    ):
        # Accept valid UUID values commonly emitted by VLESS providers, including UUIDv4 and legacy variant bits.
        if not re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            uuid,
        ):
            raise ValueError("В профиле отсутствует корректный UUID.")
    network = str(profile.get("network") or "tcp").lower()
    if network != "tcp":
        raise ValueError("Поддерживается только TCP-транспорт VLESS.")
    flow = profile.get("flow")
    if flow not in (None, "", "xtls-rprx-vision"):
        raise ValueError("Неподдерживаемый VLESS flow.")
    security = str(
        profile.get("security") or ("reality" if profile.get("reality") else "none")
    ).lower()
    reality_input = profile.get("reality")
    reality = None
    if security == "reality" or isinstance(reality_input, dict):
        reality_input = reality_input if isinstance(reality_input, dict) else {}
        public_key = str(
            reality_input.get("public_key")
            or reality_input.get("publicKey")
            or profile.get("public_key")
            or ""
        ).strip()
        server_name = str(
            reality_input.get("server_name")
            or reality_input.get("serverName")
            or profile.get("server_name")
            or ""
        ).strip()
        short_id = str(
            reality_input.get("short_id")
            if reality_input.get("short_id") is not None
            else (
                reality_input.get("shortId")
                if reality_input.get("shortId") is not None
                else profile.get("short_id") or ""
            )
        ).strip()
        fingerprint_value = reality_input.get("fingerprint") or profile.get(
            "fingerprint"
        )
        fingerprint = str(fingerprint_value).strip() if fingerprint_value else None
        if not public_key or not server_name:
            raise ValueError(
                "REALITY-профиль должен содержать публичный ключ pbk и SNI."
            )
        if not re.fullmatch(r"[0-9a-fA-F]*", short_id):
            raise ValueError("REALITY short ID должен быть шестнадцатеричной строкой.")
        reality = {
            "public_key": public_key,
            "server_name": server_name,
            "short_id": short_id,
            "fingerprint": fingerprint,
        }
    elif security not in ("none", ""):
        raise ValueError("Поддерживаются только REALITY или отсутствие TLS.")

    name = str(profile.get("name") or (address + ":" + str(port))).strip()
    if not name:
        name = address + ":" + str(port)
    if len(name) > 100:
        name = name[:100]
    try:
        profile_id = int(profile.get("id")) if profile.get("id") is not None else None
    except (TypeError, ValueError):
        profile_id = None
    if profile_id is not None and not 1 <= profile_id <= 1000000:
        profile_id = None
    return {
        "id": profile_id,
        "name": name,
        "enabled": bool(profile.get("enabled", True)),
        "address": address,
        "port": port,
        "uuid": uuid,
        "flow": flow or None,
        "network": network,
        "security": "reality" if reality else "none",
        "reality": reality,
    }


def _parse_vless_uri(source):
    source = str(source or "").strip()
    try:
        parsed = urlsplit(source)
        address = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Некорректный host или port в VLESS-ссылке.") from exc
    if parsed.scheme.lower() != "vless":
        raise ValueError("Ссылка должна начинаться с vless://.")
    user_uuid = unquote(parsed.username or "").strip()
    if not address or not user_uuid or port is None:
        raise ValueError("VLESS-ссылка должна содержать UUID, адрес и порт.")
    query = parse_qs(parsed.query, keep_blank_values=True)

    def get(name, default=None):
        values = query.get(name)
        if not values:
            return default
        value = values[0].strip()
        return value if value else default

    if (get("encryption", "none") or "none").lower() != "none":
        raise ValueError("Поддерживается только encryption=none.")
    network = (get("type", "tcp") or "tcp").lower()
    if network != "tcp":
        raise ValueError("Поддерживается только TCP-транспорт (type=tcp).")
    flow = get("flow")
    if flow not in (None, "xtls-rprx-vision"):
        raise ValueError("Поддерживается только flow=xtls-rprx-vision или пустой flow.")
    security = (get("security", "none") or "none").lower()
    reality = None
    if security == "reality":
        public_key = get("pbk")
        server_name = get("sni")
        if not public_key or not server_name:
            raise ValueError("REALITY-ссылка должна содержать параметры pbk и sni.")
        short_id = query.get("sid", [""])[0].strip()
        fingerprint = get("fp")
        reality = {
            "public_key": public_key,
            "server_name": server_name,
            "short_id": short_id,
            "fingerprint": fingerprint,
        }
    elif security not in ("none", ""):
        raise ValueError("Поддерживаются только security=reality или security=none.")
    name = unquote(parsed.fragment).strip() or address + ":" + str(port)
    return _normalize_profile(
        {
            "name": name,
            "address": address,
            "port": port,
            "uuid": user_uuid,
            "flow": flow,
            "network": network,
            "security": security,
            "reality": reality,
            "enabled": True,
        }
    )


def _parse_happ_json(source):
    try:
        document = json.loads(source)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректный JSON VLESS-профиля.") from exc
    if not isinstance(document, dict):
        raise ValueError("JSON VLESS-профиля должен быть объектом.")
    if isinstance(document.get("profiles"), list) and document.get("format") in (
        "maxvpn-vless-profiles",
        "maxvpn-vless-export",
    ):
        return document
    outbounds = document.get("outbounds")
    if not isinstance(outbounds, list):
        raise ValueError("JSON должен содержать outbounds с VLESS outbound.")
    vless = [
        item
        for item in outbounds
        if isinstance(item, dict) and item.get("protocol") == "vless"
    ]
    if len(vless) != 1:
        raise ValueError("JSON должен содержать ровно один Xray/HAPP VLESS outbound.")
    outbound = vless[0]
    settings = outbound.get("settings") or {}
    vnext = settings.get("vnext") if isinstance(settings, dict) else None
    if not isinstance(vnext, list) or not vnext or not isinstance(vnext[0], dict):
        raise ValueError("JSON VLESS outbound не содержит settings.vnext.")
    server = vnext[0]
    users = server.get("users")
    if not isinstance(users, list) or not users or not isinstance(users[0], dict):
        raise ValueError("JSON VLESS outbound не содержит users.")
    user = users[0]
    stream = outbound.get("streamSettings") or {}
    if not isinstance(stream, dict):
        raise ValueError("streamSettings должен быть объектом.")
    security = str(stream.get("security") or "none").lower()
    reality = None
    if security == "reality":
        reality_settings = stream.get("realitySettings") or {}
        if not isinstance(reality_settings, dict):
            raise ValueError("realitySettings должен быть объектом.")
        reality = {
            "public_key": reality_settings.get("publicKey"),
            "server_name": reality_settings.get("serverName"),
            "short_id": reality_settings.get("shortId", ""),
            "fingerprint": reality_settings.get("fingerprint"),
        }
    return _normalize_profile(
        {
            "name": document.get("remarks")
            or outbound.get("tag")
            or server.get("address"),
            "address": server.get("address"),
            "port": server.get("port"),
            "uuid": user.get("id"),
            "flow": user.get("flow"),
            "network": stream.get("network") or "tcp",
            "security": security,
            "reality": reality,
            "enabled": True,
        }
    )


def _identity(profile):
    reality = profile.get("reality") or {}
    return (
        str(profile.get("address", "")).lower(),
        int(profile.get("port", 0)),
        str(profile.get("uuid", "")).lower(),
        profile.get("flow"),
        profile.get("network", "tcp"),
        str(reality.get("server_name", "")).lower(),
        reality.get("public_key"),
        reality.get("short_id"),
    )


def _outbound(profile, tag):
    outbound = {
        "type": "vless",
        "tag": tag,
        "server": profile["address"],
        "server_port": int(profile["port"]),
        "uuid": profile["uuid"],
        # The profile's network='tcp' describes its VLESS stream transport.
        # Sing-box outbound.network is a separate destination-network filter;
        # setting it to tcp disables UDP and leaves urltest without a UDP member.
        # Omit that filter to enable TCP + UDP; XUDP is the VLESS UDP encoding.
        "packet_encoding": "xudp",
        "domain_resolver": "endpoint-dns",
    }
    if profile.get("flow"):
        outbound["flow"] = profile["flow"]
    reality = profile.get("reality")
    if reality:
        tls = {
            "enabled": True,
            "server_name": reality["server_name"],
            "reality": {
                "enabled": True,
                "public_key": reality["public_key"],
                "short_id": reality.get("short_id", ""),
            },
        }
        if reality.get("fingerprint"):
            tls["utls"] = {"enabled": True, "fingerprint": reality["fingerprint"]}
        outbound["tls"] = tls
    return outbound


def _render_config(store):
    enabled = [p for p in store.get("profiles", []) if p.get("enabled")]
    if not enabled:
        raise VlessControlError(
            "Включите хотя бы один VLESS-сервер перед применением конфигурации."
        )
    if len(enabled) > MAX_PROFILES:
        raise VlessControlError("В конфигурации не может быть больше 50 серверов.")
    tags = []
    outbounds = []
    ids = set()
    for profile in enabled:
        profile_id = int(profile["id"])
        if profile_id in ids:
            raise VlessControlError(
                "Найдены повторяющиеся идентификаторы VLESS-профилей."
            )
        ids.add(profile_id)
        tag = "vless-profile-" + str(profile_id)
        tags.append(tag)
        outbounds.append(_outbound(profile, tag))
    settings = store.get("settings") or {}
    interval = settings.get("urltest_interval", "3m")
    tolerance = settings.get("urltest_tolerance_ms", 50)
    if interval not in ALLOWED_INTERVALS:
        interval = "3m"
    try:
        tolerance = max(0, min(5000, int(tolerance)))
    except (TypeError, ValueError):
        tolerance = 50
    outbounds.append(
        {
            "type": "urltest",
            "tag": "vless-auto",
            "outbounds": tags,
            "url": URLTEST_URL,
            "interval": interval,
            "tolerance": tolerance,
            "interrupt_exist_connections": False,
        }
    )
    selection = store.get("selection") or {"mode": "auto", "profile_id": None}
    selected_tag = "vless-auto"
    if selection.get("mode") == "manual":
        try:
            profile_id = int(selection.get("profile_id"))
        except (TypeError, ValueError):
            profile_id = None
        if profile_id in ids:
            selected_tag = "vless-profile-" + str(profile_id)
    outbounds.append(
        {
            "type": "selector",
            "tag": "vless-out",
            "outbounds": ["vless-auto"] + tags,
            "default": selected_tag,
            "interrupt_exist_connections": False,
        }
    )
    outbounds.append({"type": "direct", "tag": "direct"})
    return {
        "log": {"level": "info", "timestamp": True},
        "dns": {
            "servers": [
                {
                    "type": "https",
                    "tag": "vless-doh",
                    "server": "1.1.1.1",
                    "server_port": 443,
                    "path": "/dns-query",
                    "tls": {"enabled": True, "server_name": "cloudflare-dns.com"},
                    "detour": "vless-out",
                },
                {
                    "type": "udp",
                    "tag": "endpoint-dns",
                    "server": "1.1.1.1",
                    "server_port": 53,
                    "routing_mark": 100,
                },
            ],
            "final": "vless-doh",
            "strategy": "prefer_ipv4",
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "maxvpn-tun-in",
                "interface_name": "maxvpn0",
                "address": ["172.19.0.1/30"],
                "mtu": 1380,
                "auto_route": False,
            }
        ],
        "outbounds": outbounds,
        "route": {
            "rules": [{"port": 53, "action": "hijack-dns"}],
            "default_domain_resolver": "endpoint-dns",
            "auto_detect_interface": True,
            "final": "vless-out",
        },
        "experimental": {
            "clash_api": {"external_controller": "127.0.0.1:9090", "secret": ""}
        },
    }


def _selection_interval_seconds(value):
    """Parse a sing-box URLTest interval such as 30s, 3m, or 1h."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smh])\s*", value.lower())
    if not match:
        return None
    amount = float(match.group(1))
    multiplier = {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    seconds = amount * multiplier
    return int(seconds) if seconds > 0 else None


def _selection_timestamp_epoch(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip()
    # sing-box can return fractional timestamps with nanosecond precision
    # (for example, .842531674Z). Older Python versions used by OpenWrt
    # accept only six fractional digits in datetime.fromisoformat(). Truncate
    # to microseconds before parsing; this is far more precise than the 15 s
    # monitor interval and avoids marking valid measurements as missing.
    fraction_match = re.match(
        r"^(.*[T ]\d{2}:\d{2}:\d{2})\.(\d+)(Z|[+-]\d{2}:\d{2})?$",
        text,
    )
    if fraction_match:
        prefix, fraction, zone = fraction_match.groups()
        text = prefix + "." + fraction[:6] + (zone or "")

    try:
        parsed = _selection_datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_selection_datetime.timezone.utc)
        return parsed.timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _selection_sample_age(observed_epoch, sample, interval_seconds):
    if not isinstance(sample, dict):
        return None, False, False
    delay = sample.get("delay_ms")
    has_delay = (
        isinstance(delay, (int, float)) and not isinstance(delay, bool) and delay >= 0
    )
    sample_epoch = _selection_timestamp_epoch(sample.get("observed_at"))
    if observed_epoch is None or sample_epoch is None:
        return None, False, has_delay
    age = observed_epoch - sample_epoch
    # A small negative delta can occur because snapshot timestamps and API history
    # timestamps are collected sequentially. Large future deltas are not trustworthy.
    if age < -5:
        return None, False, has_delay
    age_seconds = int(max(0.0, age))
    fresh = bool(
        has_delay and interval_seconds is not None and age_seconds <= interval_seconds
    )
    return age_seconds, fresh, has_delay


def _selection_event_diagnostics(
    *,
    previous_sample,
    active_sample,
    observed_epoch,
    interval,
    tolerance,
    selection_mode,
    previous_mode,
    reason,
    gap_seconds,
):
    interval_seconds = _selection_interval_seconds(interval)
    previous_age, previous_fresh, previous_has_delay = _selection_sample_age(
        observed_epoch, previous_sample, interval_seconds
    )
    active_age, active_fresh, active_has_delay = _selection_sample_age(
        observed_epoch, active_sample, interval_seconds
    )
    both_measured = previous_has_delay and active_has_delay
    if (
        interval_seconds is None
        or not both_measured
        or previous_age is None
        or active_age is None
    ):
        freshness = "incomplete"
    elif not previous_fresh or not active_fresh:
        freshness = "stale"
    else:
        freshness = "fresh"

    previous_delay = (
        previous_sample.get("delay_ms") if isinstance(previous_sample, dict) else None
    )
    active_delay = (
        active_sample.get("delay_ms") if isinstance(active_sample, dict) else None
    )
    improvement = None
    if (
        isinstance(previous_delay, (int, float))
        and not isinstance(previous_delay, bool)
        and isinstance(active_delay, (int, float))
        and not isinstance(active_delay, bool)
    ):
        improvement = int(previous_delay - active_delay)

    if reason == "observation_gap" or (gap_seconds is not None and gap_seconds > 45):
        status = "observation_gap"
        details = (
            "Между наблюдениями был длительный перерыв; смена могла произойти в любой момент "
            "этого периода. Измерения не позволяют установить причину."
        )
    elif reason == "selection_mode_changed" or previous_mode != selection_mode:
        status = "selection_mode_changed"
        details = "Изменился режим выбора (автоматический/ручной); источник действия по API не установлен."
    elif selection_mode != "auto" or previous_mode != "auto":
        status = "manual_selection"
        details = "Событие относится к ручному режиму выбора, а не к решению URLTest."
    elif freshness == "incomplete":
        status = "insufficient_data"
        details = (
            "Недостаточно данных: для одного или обоих серверов отсутствует числовая задержка, "
            "временная отметка или корректный интервал URLTest. Причина не установлена."
        )
    elif freshness == "stale":
        status = "stale_measurements"
        details = (
            f"Как минимум одно последнее измерение старше интервала URLTest ({interval_seconds} с): "
            f"предыдущий сервер — {previous_age} с, новый — {active_age} с. "
            "Эти данные не позволяют надёжно объяснить переключение."
        )
    elif not isinstance(tolerance, int) or isinstance(tolerance, bool) or tolerance < 0:
        status = "insufficient_configuration"
        details = "Оба измерения свежие, но корректный допуск URLTest неизвестен; вывод о выборе ограничен."
    elif improvement is not None and improvement >= tolerance:
        status = "consistent_with_latest_delays"
        details = (
            f"Оба измерения свежие. Новый сервер быстрее предыдущего на {improvement} мс, "
            f"что соответствует допуску {tolerance} мс. Это согласуется с выбором, но не "
            "доказывает внутреннюю причину решения sing-box."
        )
    else:
        status = "not_explained_by_latest_delays"
        delta_text = "не вычислена" if improvement is None else f"{improvement} мс"
        details = (
            f"Оба измерения свежие, но разница (предыдущая задержка минус новая) равна {delta_text}; "
            f"этого недостаточно, чтобы объяснить переключение через допуск {tolerance} мс. "
            "Это не доказывает ошибку sing-box: API не раскрывает фактическую причину."
        )

    return {
        "previous_delay_age_seconds": previous_age,
        "active_delay_age_seconds": active_age,
        "previous_delay_fresh": previous_fresh if previous_age is not None else None,
        "active_delay_fresh": active_fresh if active_age is not None else None,
        "measurement_freshness": freshness,
        "delay_improvement_ms": improvement,
        "diagnostic_status": status,
        "diagnostic_details": details,
    }


class VlessControl:
    def __init__(
        self,
        profile_file=None,
        config_file=None,
        command_runner=None,
        selection_history_file=None,
    ):
        self.profile_file = Path(profile_file or PROFILE_FILE)
        self.config_file = Path(config_file or CONFIG_FILE)
        self.command_runner = command_runner or _run
        self.selection_history_file = Path(
            selection_history_file or DATA / "vless-selection-history.json"
        )
        self.wan_fallback_state_file = self.profile_file.with_name(
            "vless-wan-fallback.json"
        )
        self._last_selection_snapshot = None
        self._wan_fallback_runtime_failures = 0
        self._wan_fallback_profile_counters = {}
        self._wan_fallback_probe_scope = None

    def _reset_wan_fallback_monitor_state(self):
        self._wan_fallback_runtime_failures = 0
        self._wan_fallback_profile_counters = {}
        self._wan_fallback_probe_scope = None

    def _exec(self, args, timeout=12, check=False, input_text=None):
        try:
            return self.command_runner(
                args, timeout=timeout, check=check, input_text=input_text
            )
        except TypeError:
            # Compatibility for tiny test doubles accepting only args.
            return self.command_runner(args)

    def _checked(self, args, action, timeout=20, input_text=None):
        result = self._exec(args, timeout=timeout, input_text=input_text)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            detail = re.sub(r"\s+", " ", detail)[:400]
            raise VlessControlError(action + (": " + detail if detail else "."))
        return result

    def _read_mode(self):
        try:
            mode = MODE_FILE.read_text(encoding="utf-8").strip().lower()
        except OSError:
            return "unknown"
        return mode if mode in ("wan", "vpn", "vless") else "unknown"

    def _running(self):
        result = self._exec(
            [
                "ubus",
                "call",
                "service",
                "list",
                json.dumps(
                    {"name": "maxvpn-sing-box", "verbose": True}, separators=(",", ":")
                ),
            ],
            timeout=4,
        )
        if result.returncode == 0:
            try:
                payload = json.loads(result.stdout or "{}")
                service = payload.get("maxvpn-sing-box")
                instances = (
                    service.get("instances") if isinstance(service, dict) else None
                )
                if isinstance(instances, dict):
                    return any(
                        isinstance(i, dict) and i.get("running") is True
                        for i in instances.values()
                    )
            except (ValueError, TypeError, AttributeError):
                pass
        check = self._exec(
            [
                "pgrep",
                "-f",
                r"/usr/bin/sing-box run -c /etc/maxvpn/sing-box-vless.json",
            ],
            timeout=3,
        )
        return check.returncode == 0

    def _read_installed_config(self):
        return _read_json_file(self.config_file)

    def _profile_from_outbound(self, outbound, profile_id, enabled=True):
        tls = outbound.get("tls") if isinstance(outbound.get("tls"), dict) else {}
        reality = tls.get("reality") if isinstance(tls.get("reality"), dict) else None
        reality_value = None
        security = "none"
        if reality and reality.get("enabled"):
            security = "reality"
            reality_value = {
                "public_key": reality.get("public_key") or reality.get("publicKey"),
                "server_name": tls.get("server_name") or tls.get("serverName"),
                "short_id": reality.get("short_id") or reality.get("shortId") or "",
                "fingerprint": (
                    (tls.get("utls") or {}).get("fingerprint")
                    if isinstance(tls.get("utls") or {}, dict)
                    else None
                ),
            }
        server = outbound.get("server")
        port = outbound.get("server_port")
        if not server or not port or not outbound.get("uuid"):
            return None
        try:
            profile = _normalize_profile(
                {
                    "id": profile_id,
                    "name": str(server) + ":" + str(port),
                    "enabled": enabled,
                    "address": server,
                    "port": port,
                    "uuid": outbound.get("uuid"),
                    "flow": outbound.get("flow"),
                    "network": outbound.get("network") or "tcp",
                    "security": security,
                    "reality": reality_value,
                }
            )
            return profile
        except ValueError:
            return None

    def _seed_from_config(self):
        config = self._read_installed_config()
        if not isinstance(config, dict):
            return {
                "version": 1,
                "profiles": [],
                "settings": {
                    "urltest_interval": "3m",
                    "urltest_tolerance_ms": 50,
                    "wan_fallback_enabled": False,
                },
                "selection": {"mode": "auto", "profile_id": None},
            }
        outbounds = config.get("outbounds")
        if not isinstance(outbounds, list):
            outbounds = []
        by_id = {}
        for outbound in outbounds:
            if not isinstance(outbound, dict) or outbound.get("type") != "vless":
                continue
            tag = str(outbound.get("tag") or "")
            match = re.fullmatch(r"vless-profile-([1-9][0-9]*)", tag)
            if match:
                profile_id = int(match.group(1))
                prof = self._profile_from_outbound(outbound, profile_id, False)
                if prof:
                    by_id[profile_id] = prof
        auto = next(
            (
                o
                for o in outbounds
                if isinstance(o, dict)
                and o.get("type") == "urltest"
                and o.get("tag") == "vless-auto"
            ),
            None,
        )
        active_tags = (
            set(auto.get("outbounds", [])) if isinstance(auto, dict) else set()
        )
        if by_id:
            for profile_id, profile in by_id.items():
                profile["enabled"] = (
                    ("vless-profile-" + str(profile_id)) in active_tags
                    if isinstance(auto, dict)
                    else True
                )
            auto_interval = (
                auto.get("interval", "3m") if isinstance(auto, dict) else "3m"
            )
            auto_tolerance = auto.get("tolerance", 50) if isinstance(auto, dict) else 50
            selector = next(
                (
                    o
                    for o in outbounds
                    if isinstance(o, dict)
                    and o.get("type") == "selector"
                    and o.get("tag") == "vless-out"
                ),
                None,
            )
            default = (
                selector.get("default", "vless-auto")
                if isinstance(selector, dict)
                else "vless-auto"
            )
            selection = {"mode": "auto", "profile_id": None}
            if re.fullmatch(r"vless-profile-([1-9][0-9]*)", str(default)):
                selection = {
                    "mode": "manual",
                    "profile_id": int(default.rsplit("-", 1)[1]),
                }
            return {
                "version": 1,
                "profiles": sorted(by_id.values(), key=lambda p: p["id"]),
                "settings": {
                    "urltest_interval": (
                        auto_interval if auto_interval in ALLOWED_INTERVALS else "3m"
                    ),
                    "urltest_tolerance_ms": auto_tolerance,
                    "wan_fallback_enabled": False,
                },
                "selection": selection,
            }
        # Legacy single-server configuration: only seed the final VLESS outbound.
        route = config.get("route") if isinstance(config.get("route"), dict) else {}
        final_tag = route.get("final", "vless-out")
        single = next(
            (
                o
                for o in outbounds
                if isinstance(o, dict)
                and o.get("type") == "vless"
                and o.get("tag") == final_tag
            ),
            None,
        )
        if single is None:
            single = next(
                (
                    o
                    for o in outbounds
                    if isinstance(o, dict) and o.get("type") == "vless"
                ),
                None,
            )
        if single:
            profile = self._profile_from_outbound(single, 1, True)
            if profile:
                return {
                    "version": 1,
                    "profiles": [profile],
                    "settings": {
                        "urltest_interval": "3m",
                        "urltest_tolerance_ms": 50,
                        "wan_fallback_enabled": False,
                    },
                    "selection": {"mode": "auto", "profile_id": None},
                }
        return {
            "version": 1,
            "profiles": [],
            "settings": {
                "urltest_interval": "3m",
                "urltest_tolerance_ms": 50,
                "wan_fallback_enabled": False,
            },
            "selection": {"mode": "auto", "profile_id": None},
        }

    def _load_store(self, seed=True):
        if self.profile_file.is_file():
            try:
                store = json.loads(self.profile_file.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise VlessControlError(
                    "Файл профилей VLESS повреждён; существующий файл сохранён без изменений."
                ) from exc
            if not isinstance(store, dict) or not isinstance(
                store.get("profiles"), list
            ):
                raise VlessControlError("Формат хранилища VLESS не распознан.")
            store.setdefault("version", 1)
            store.setdefault(
                "settings",
                {
                    "urltest_interval": "3m",
                    "urltest_tolerance_ms": 50,
                    "wan_fallback_enabled": False,
                },
            )
            if not isinstance(store["settings"], dict):
                store["settings"] = {}
            store["settings"].setdefault("urltest_interval", "3m")
            store["settings"].setdefault("urltest_tolerance_ms", 50)
            store["settings"].setdefault("wan_fallback_enabled", False)
            store.setdefault("selection", {"mode": "auto", "profile_id": None})
            return store
        if seed:
            store = self._seed_from_config()
        else:
            store = {
                "version": 1,
                "profiles": [],
                "settings": {
                    "urltest_interval": "3m",
                    "urltest_tolerance_ms": 50,
                    "wan_fallback_enabled": False,
                },
                "selection": {"mode": "auto", "profile_id": None},
            }
        self._save_store(store, backup=False)
        return store

    def _save_store(self, store, backup=True):
        path = self.profile_file
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            try:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                os.chmod(BACKUP_DIR, 0o700)
                backup_path = BACKUP_DIR / (
                    "profiles-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
                )
                shutil.copy2(str(path), str(backup_path))
                os.chmod(backup_path, 0o600)
            except OSError as exc:
                raise VlessControlError(
                    "Не удалось создать резервную копию хранилища VLESS."
                ) from exc
        content = (
            json.dumps(store, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        fd, temporary = tempfile.mkstemp(
            prefix=".vless-profiles-", dir=str(path.parent)
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, str(path))
            os.chmod(path, 0o600)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def _profile_list(self, store, include_secrets=False):
        result = []
        for p in sorted(
            store.get("profiles", []), key=lambda x: int(x.get("id", 999999))
        ):
            row = {
                k: p.get(k)
                for k in (
                    "id",
                    "name",
                    "enabled",
                    "address",
                    "port",
                    "flow",
                    "network",
                    "security",
                )
            }
            reality = p.get("reality") or {}
            row["server_name"] = reality.get("server_name")
            row["fingerprint"] = reality.get("fingerprint")
            row["has_uuid"] = bool(p.get("uuid"))
            if include_secrets:
                row["uuid"] = p.get("uuid")
                row["reality"] = copy.deepcopy(reality)
            result.append(row)
        return result

    def _desired_selection(self, store):
        """Return the saved selection intent without confusing it with live runtime."""
        selection = (
            store.get("selection") if isinstance(store.get("selection"), dict) else {}
        )
        requested_mode = selection.get("mode")
        try:
            requested_profile_id = int(selection.get("profile_id"))
        except (TypeError, ValueError):
            requested_profile_id = None

        enabled_ids = {
            int(profile.get("id", -1))
            for profile in store.get("profiles", [])
            if isinstance(profile, dict) and profile.get("enabled")
        }
        if requested_mode == "manual" and requested_profile_id in enabled_ids:
            return (
                "manual",
                requested_profile_id,
                f"vless-profile-{requested_profile_id}",
            )
        return "auto", None, "vless-auto"

    def _runtime_info(self, store):
        installed = (
            self.config_file.is_file() and SING_BOX.exists() and SERVICE.exists()
        )
        running = self._running() if installed else False
        selected = active = None
        # This field describes the running sing-box process only. The saved
        # choice is exposed separately below and may still need Apply/restart.
        selection_mode = "unknown"
        active_address = None
        active_port = None
        if running:
            selected_payload = self._exec(
                [
                    "curl",
                    "-fsS",
                    "--max-time",
                    "3",
                    "http://127.0.0.1:9090/proxies/vless-out",
                ],
                timeout=4,
            )
            if selected_payload.returncode == 0:
                try:
                    value = json.loads(selected_payload.stdout or "{}")
                    selected = value.get("now") if isinstance(value, dict) else None
                except ValueError:
                    selected = None
            if selected == "vless-auto":
                active_payload = self._exec(
                    [
                        "curl",
                        "-fsS",
                        "--max-time",
                        "3",
                        "http://127.0.0.1:9090/proxies/vless-auto",
                    ],
                    timeout=4,
                )
                if active_payload.returncode == 0:
                    try:
                        value = json.loads(active_payload.stdout or "{}")
                        active = value.get("now") if isinstance(value, dict) else None
                    except ValueError:
                        active = None
                selection_mode = "auto"
            elif isinstance(selected, str) and re.fullmatch(
                r"vless-profile-[1-9][0-9]*", selected
            ):
                active = selected
                selection_mode = "manual"
            if isinstance(active, str):
                match = re.fullmatch(r"vless-profile-([1-9][0-9]*)", active)
                if match:
                    profile = next(
                        (
                            p
                            for p in store.get("profiles", [])
                            if int(p.get("id", -1)) == int(match.group(1))
                        ),
                        None,
                    )
                    if profile:
                        active_address = profile.get("address")
                        active_port = profile.get("port")
            if not active_address:
                config = self._read_installed_config() or {}
                outbounds = (
                    config.get("outbounds", []) if isinstance(config, dict) else []
                )
                if isinstance(outbounds, list):
                    item = next(
                        (
                            o
                            for o in outbounds
                            if isinstance(o, dict) and o.get("tag") == active
                        ),
                        None,
                    )
                    if item:
                        active_address = item.get("server")
                        active_port = item.get("server_port")
        desired_mode, desired_profile_id, desired_outbound = self._desired_selection(
            store
        )
        mode = self._read_mode()
        interface_up = False
        if mode == "vless" and running:
            interface_result = self._exec(
                ["ip", "link", "show", "dev", "maxvpn0"], timeout=3
            )
            if interface_result.returncode == 0:
                interface_up = bool(
                    re.search(r"<[^>]*\bUP\b[^>]*>", interface_result.stdout or "")
                )
        route_healthy = mode != "vless" or (running and interface_up)
        route_health = "ok" if mode != "vless" or route_healthy else "degraded"
        selection_pending = bool(store.get("profiles")) and (
            not running or selected != desired_outbound
        )
        return {
            "installed": bool(installed),
            "running": bool(running),
            "interface": "maxvpn0",
            "traffic_mode": mode,
            "lan_routing_enabled": mode == "vless",
            "lan_route_healthy": bool(route_healthy),
            "route_health": route_health,
            "tun_interface_up": bool(interface_up),
            "selected_outbound": selected,
            "active_outbound": active,
            "active_server_address": active_address,
            "active_server_port": active_port,
            "selection_mode": selection_mode,
            "desired_selection_mode": desired_mode,
            "desired_profile_id": desired_profile_id,
            "desired_outbound": desired_outbound,
            "selection_pending": selection_pending,
            "profiles": self._profile_list(store),
            "settings": copy.deepcopy(
                store.get("settings")
                or {
                    "urltest_interval": "3m",
                    "urltest_tolerance_ms": 50,
                    "wan_fallback_enabled": False,
                }
            ),
            "wan_fallback_active": self._load_wan_fallback_state().get("active")
            is True,
            "enabled_count": sum(
                1 for p in store.get("profiles", []) if p.get("enabled")
            ),
            "profile_limit": MAX_PROFILES,
            "config_dirty": self._config_differs(store),
        }

    def _config_differs(self, store):
        current = self._read_installed_config()
        if not isinstance(current, dict):
            return bool(store.get("profiles"))
        try:
            desired = _render_config(store)
        except (ValueError, VlessControlError, KeyError, TypeError):
            return True
        # Canonical equality avoids restarts for irrelevant JSON whitespace/order.
        return json.dumps(current, sort_keys=True, separators=(",", ":")) != json.dumps(
            desired, sort_keys=True, separators=(",", ":")
        )

    def get_state(self):
        with LOCK:
            store = self._load_store()
            return self._runtime_info(store)

    @_serialized
    def import_profiles(self, data):
        if not isinstance(data, dict):
            raise VlessControlError("Данные импорта должны быть JSON-объектом.")
        store = self._load_store()
        rows = data.get("profiles")
        settings = data.get("settings")
        if rows is None:
            sources = data.get("sources")
            if isinstance(sources, list):
                rows = [{"source": source} for source in sources]
            else:
                sources_text = data.get("text")
                if isinstance(sources_text, str):
                    rows = [
                        {"source": line.strip()}
                        for line in sources_text.splitlines()
                        if line.strip()
                    ]
        if not isinstance(rows, list) or not rows:
            raise VlessControlError(
                "Не найдены VLESS-ссылки или массив profiles в файле экспорта."
            )
        if len(rows) > MAX_PROFILES:
            raise VlessControlError(
                "За один импорт можно передать не более 50 профилей."
            )
        current = list(store.get("profiles", []))
        identities = {_identity(p): p for p in current}
        ids = {int(p["id"]) for p in current}
        imported = updated = duplicates = failed = 0
        results = []
        max_id = max(ids or {0})
        for idx, row in enumerate(rows, 1):
            try:
                if isinstance(row, str):
                    source = row
                    entry = {}
                elif isinstance(row, dict):
                    source = row.get("source") or row.get("uri") or ""
                    entry = row
                else:
                    raise ValueError("Строка профиля имеет неизвестный формат.")
                source = str(source).strip()
                if not source:
                    raise ValueError("Ссылка VLESS пустая.")
                if source.startswith("vless://"):
                    parsed = _parse_vless_uri(source)
                elif source.startswith("{"):
                    parsed_doc = _parse_happ_json(source)
                    if isinstance(parsed_doc, dict) and isinstance(
                        parsed_doc.get("profiles"), list
                    ):
                        raise ValueError(
                            "Вложенный пакет экспорта не поддерживается в строке профиля."
                        )
                    parsed = parsed_doc
                else:
                    raise ValueError("Ожидается vless:// ссылка или JSON Xray/HAPP.")
                if entry.get("name"):
                    parsed["name"] = (
                        str(entry.get("name")).strip()[:100] or parsed["name"]
                    )
                if "enabled" in entry:
                    parsed["enabled"] = bool(entry.get("enabled"))
                desired_id = entry.get("id")
                try:
                    desired_id = int(desired_id) if desired_id is not None else None
                except (TypeError, ValueError):
                    desired_id = None
                identity = _identity(parsed)
                existing = identities.get(identity)
                if existing:
                    # A localhost export maps back to the profiles that seeded from the active sing-box tags.
                    existing["name"] = parsed["name"]
                    existing["enabled"] = parsed["enabled"]
                    existing.update(
                        {
                            k: parsed[k]
                            for k in (
                                "address",
                                "port",
                                "uuid",
                                "flow",
                                "network",
                                "security",
                                "reality",
                            )
                        }
                    )
                    updated += 1
                    results.append(
                        {
                            "index": idx,
                            "status": "updated",
                            "profile_id": existing["id"],
                        }
                    )
                    continue
                if len(current) >= MAX_PROFILES:
                    raise ValueError("Достигнут лимит 50 профилей.")
                if desired_id and desired_id not in ids:
                    profile_id = desired_id
                else:
                    max_id += 1
                    while max_id in ids:
                        max_id += 1
                    profile_id = max_id
                parsed["id"] = profile_id
                current.append(parsed)
                ids.add(profile_id)
                identities[identity] = parsed
                imported += 1
                results.append(
                    {"index": idx, "status": "imported", "profile_id": profile_id}
                )
            except (ValueError, TypeError, KeyError) as exc:
                failed += 1
                results.append(
                    {"index": idx, "status": "invalid", "reason": str(exc)[:180]}
                )
        if not imported and not updated:
            raise VlessControlError(
                "Импорт не изменил список серверов: исправьте ошибки или проверьте дубликаты."
            )
        store["profiles"] = current
        if isinstance(settings, dict):
            interval = settings.get(
                "urltest_interval",
                store.get("settings", {}).get("urltest_interval", "3m"),
            )
            tolerance = settings.get(
                "urltest_tolerance_ms",
                store.get("settings", {}).get("urltest_tolerance_ms", 50),
            )
            if interval in ALLOWED_INTERVALS:
                store.setdefault("settings", {})["urltest_interval"] = interval
            try:
                store.setdefault("settings", {})["urltest_tolerance_ms"] = max(
                    0, min(5000, int(tolerance))
                )
            except (TypeError, ValueError):
                pass
        self._save_store(store)
        return {
            "imported": imported,
            "updated": updated,
            "duplicates": duplicates,
            "failed": failed,
            "total": len(rows),
            "items": results,
            "profiles": self._profile_list(store),
        }

    @_serialized
    def update_profile(self, profile_id, data):
        store = self._load_store()
        profile = next(
            (
                p
                for p in store.get("profiles", [])
                if int(p.get("id", -1)) == int(profile_id)
            ),
            None,
        )
        if profile is None:
            raise VlessControlError("VLESS-профиль не найден.")
        if "name" in data:
            name = str(data.get("name") or "").strip()
            if not name or len(name) > 100:
                raise VlessControlError(
                    "Название должно содержать от 1 до 100 символов."
                )
            profile["name"] = name
        if "enabled" in data:
            enabled = bool(data.get("enabled"))
            if (
                profile["enabled"]
                and not enabled
                and sum(1 for p in store["profiles"] if p.get("enabled")) <= 1
            ):
                raise VlessControlError(
                    "Нельзя отключить последний включённый VLESS-сервер."
                )
            profile["enabled"] = enabled
            selection = store.get("selection") or {}
            if (
                not enabled
                and selection.get("mode") == "manual"
                and selection.get("profile_id") == int(profile_id)
            ):
                store["selection"] = {"mode": "auto", "profile_id": None}
        self._save_store(store)
        return self._runtime_info(store)

    @_serialized
    def delete_profile(self, profile_id):
        store = self._load_store()
        profiles = store.get("profiles", [])
        profile = next(
            (p for p in profiles if int(p.get("id", -1)) == int(profile_id)), None
        )
        if profile is None:
            raise VlessControlError("VLESS-профиль не найден.")
        if profile.get("enabled") and sum(1 for p in profiles if p.get("enabled")) <= 1:
            raise VlessControlError("Нельзя удалить последний включённый VLESS-сервер.")
        store["profiles"] = [
            p for p in profiles if int(p.get("id", -1)) != int(profile_id)
        ]
        selection = store.get("selection") or {}
        if selection.get("profile_id") == int(profile_id):
            store["selection"] = {"mode": "auto", "profile_id": None}
        self._save_store(store)
        return self._runtime_info(store)

    @_serialized
    def update_settings(self, data):
        store = self._load_store()
        interval = data.get(
            "urltest_interval", store.get("settings", {}).get("urltest_interval", "3m")
        )
        tolerance = data.get(
            "urltest_tolerance_ms",
            store.get("settings", {}).get("urltest_tolerance_ms", 50),
        )
        if interval not in ALLOWED_INTERVALS:
            raise VlessControlError("Недопустимый интервал автовыбора.")
        try:
            tolerance = int(tolerance)
        except (TypeError, ValueError) as exc:
            raise VlessControlError("Допуск переключения должен быть числом.") from exc
        if not 0 <= tolerance <= 5000:
            raise VlessControlError("Допуск переключения должен быть от 0 до 5000 мс.")
        wan_fallback_enabled = data.get(
            "wan_fallback_enabled",
            store.get("settings", {}).get("wan_fallback_enabled", False),
        )
        if not isinstance(wan_fallback_enabled, bool):
            raise VlessControlError(
                "Политика перехода на WAN должна быть включена или выключена."
            )
        fallback_state = self._load_wan_fallback_state()
        if not wan_fallback_enabled and fallback_state.get("active") is True:
            if self._read_mode() == "wan":
                try:
                    self.set_mode("vless", automatic_fallback=True)
                except Exception as exc:
                    raise VlessControlError(
                        "Не удалось вернуть LAN в VLESS; политика WAN fallback оставлена включённой."
                    ) from exc
            fallback_state["active"] = False
            fallback_state["selection_mode"] = None
            fallback_state["fallback_started_at"] = None
            fallback_state["profile_counters"] = {}
            fallback_state["probe_scope"] = None
            fallback_state["runtime_consecutive_failures"] = 0
            self._reset_wan_fallback_monitor_state()
            self._save_wan_fallback_state(fallback_state)
        store["settings"] = {
            "urltest_interval": interval,
            "urltest_tolerance_ms": tolerance,
            "wan_fallback_enabled": wan_fallback_enabled,
        }
        self._save_store(store)
        return self._runtime_info(store)

    def _write_config_atomic(self, config):
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=".sing-box-vless-", dir=str(self.config_file.parent)
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(
                    json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n"
                )
                output.flush()
                os.fsync(output.fileno())
            check = self._exec([str(SING_BOX), "check", "-c", temporary], timeout=20)
            if check.returncode != 0:
                detail = re.sub(
                    r"\s+", " ", (check.stderr or check.stdout or "").strip()
                )[:350]
                raise VlessControlError(
                    "Проверка новой конфигурации sing-box не пройдена"
                    + (": " + detail if detail else ".")
                )
            os.replace(temporary, str(self.config_file))
            os.chmod(self.config_file, 0o600)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def _make_backup(self):
        if not self.config_file.is_file():
            return None
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(BACKUP_DIR, 0o700)
        backup = BACKUP_DIR / (
            "sing-box-vless-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
        )
        shutil.copy2(str(self.config_file), str(backup))
        os.chmod(backup, 0o600)
        try:
            backups = sorted(
                BACKUP_DIR.glob("sing-box-vless-*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for old in backups[10:]:
                old.unlink()
        except OSError:
            pass
        return backup

    def apply_config(self, start=False):
        with LOCK:
            store = self._load_store()
            if not SING_BOX.is_file() or not os.access(str(SING_BOX), os.X_OK):
                raise VlessControlError("/usr/bin/sing-box не установлен.")
            if not SERVICE.is_file() or not os.access(str(SERVICE), os.X_OK):
                raise VlessControlError(
                    "Сервис /etc/init.d/maxvpn-sing-box не установлен."
                )
            config = _render_config(store)
            # Validate before stopping/replacing the currently running process.
            check_fd, check_path = tempfile.mkstemp(
                prefix=".sing-box-check-", dir=str(self.config_file.parent)
            )
            try:
                os.fchmod(check_fd, 0o600)
                with os.fdopen(check_fd, "w", encoding="utf-8") as out:
                    json.dump(config, out, ensure_ascii=False, indent=2)
                    out.write("\n")
                check = self._exec(
                    [str(SING_BOX), "check", "-c", check_path], timeout=20
                )
                if check.returncode != 0:
                    detail = re.sub(
                        r"\s+", " ", (check.stderr or check.stdout or "").strip()
                    )[:350]
                    raise VlessControlError(
                        "Проверка конфигурации sing-box не пройдена"
                        + (": " + detail if detail else ".")
                    )
            finally:
                try:
                    os.unlink(check_path)
                except OSError:
                    pass
            was_running = self._running()
            old_mode = self._read_mode()
            backup = self._make_backup()
            try:
                if was_running:
                    self._checked(
                        [str(SERVICE), "stop"],
                        "Не удалось остановить sing-box",
                        timeout=20,
                    )
                self._write_config_atomic(config)
                if was_running or start:
                    self._checked(
                        [str(SERVICE), "start"],
                        "Не удалось запустить sing-box с новой конфигурацией",
                        timeout=25,
                    )
                    self._checked(
                        [str(SERVICE), "enable"],
                        "Не удалось включить автозапуск sing-box",
                        timeout=10,
                    )
                    deadline = time.time() + 6
                    while time.time() < deadline:
                        if self._running():
                            info = self._runtime_info(store)
                            if old_mode != "vless" or info.get("lan_route_healthy"):
                                return info
                        time.sleep(0.4)
                    raise VlessControlError(
                        "sing-box или интерфейс maxvpn0 не подтвердил готовность после применения конфигурации."
                    )
                return self._runtime_info(store)
            except Exception as primary:
                rollback_ok = False
                try:
                    if self._running():
                        self._exec([str(SERVICE), "stop"], timeout=15)
                    if backup and backup.is_file():
                        tmp = self.config_file.with_name(
                            ".sing-box-rollback-" + str(os.getpid())
                        )
                        shutil.copy2(str(backup), str(tmp))
                        os.chmod(tmp, 0o600)
                        os.replace(str(tmp), str(self.config_file))
                        if was_running or start:
                            restored = self._exec([str(SERVICE), "start"], timeout=25)
                            rollback_ok = restored.returncode == 0 and self._running()
                            if rollback_ok and old_mode == "vless":
                                rollback_ok = self._runtime_info(
                                    self._load_store()
                                ).get("lan_route_healthy", False)
                        else:
                            rollback_ok = True
                    elif not was_running:
                        try:
                            self.config_file.unlink()
                        except OSError:
                            pass
                        rollback_ok = not start
                except Exception:
                    rollback_ok = False
                if not rollback_ok and old_mode == "vless":
                    self._exec(["/usr/bin/vpn-lan-vless-on"], timeout=12)
                message = str(primary)
                if not rollback_ok:
                    message += " Откат конфигурации не подтверждён; выполнена попытка сохранить для LAN маршрут VLESS с fail-closed поведением."
                else:
                    message += " Предыдущая конфигурация восстановлена."
                raise VlessControlError(message) from primary

    def start(self):
        with LOCK:
            # A stopped runtime must be started from the currently saved profile set.
            if not self._running() or self._config_differs(self._load_store()):
                return self.apply_config(start=True)
            self._checked(
                [str(SERVICE), "start"], "Не удалось запустить sing-box", timeout=25
            )
            self._checked(
                [str(SERVICE), "enable"],
                "Не удалось включить автозапуск sing-box",
                timeout=10,
            )
            if not self._running():
                raise VlessControlError("Сервис sing-box не подтвердил запуск.")
            return self._runtime_info(self._load_store())

    def stop(self):
        with LOCK:
            fallback_state = self._load_wan_fallback_state()
            fallback_state["active"] = False
            fallback_state["selection_mode"] = None
            fallback_state["fallback_started_at"] = None
            fallback_state["profile_counters"] = {}
            fallback_state["probe_scope"] = None
            fallback_state["runtime_consecutive_failures"] = 0
            self._reset_wan_fallback_monitor_state()
            self._save_wan_fallback_state(fallback_state)
            try:
                self._checked(
                    [VLESS_STOP_HELPER],
                    "Не удалось безопасно остановить sing-box",
                    timeout=40,
                )
            except FileNotFoundError as exc:
                raise VlessControlError(
                    "Обновите скрипты маршрутизации MaxVPN перед остановкой sing-box."
                ) from exc
            if self._running():
                raise VlessControlError(
                    "sing-box продолжает работать после команды остановки."
                )
            return self._runtime_info(self._load_store())

    @_serialized
    def select_outbound(self, profile_id=None):
        """Save a desired selection; the running route changes only after Apply/restart."""
        store = self._load_store()
        if not self._running():
            raise VlessControlError("Сначала запустите sing-box.")

        if profile_id is None:
            selection = {"mode": "auto", "profile_id": None}
        else:
            try:
                profile_id = int(profile_id)
            except (TypeError, ValueError) as exc:
                raise VlessControlError("Некорректный идентификатор сервера.") from exc
            profile = next(
                (
                    p
                    for p in store.get("profiles", [])
                    if int(p.get("id", -1)) == profile_id
                ),
                None,
            )
            if profile is None or not profile.get("enabled"):
                raise VlessControlError("Выбранный сервер не найден или отключён.")
            selection = {"mode": "manual", "profile_id": profile_id}

        # Do not PUT /proxies/vless-out here. This button stages intent only;
        # Apply/restart is the sole operation that installs the new selector
        # default and causes the running service to load it.
        store["selection"] = selection
        self._save_store(store)
        result = self._runtime_info(store)
        result["action"] = "selection-staged"
        result["message"] = (
            "Режим автовыбора сохранён для следующего применения. Текущий sing-box не изменён."
            if profile_id is None
            else "Ручной сервер сохранён для следующего применения. Текущий sing-box не изменён."
        )
        return result

    def _load_delay_history(self):
        path = Path(DELAY_HISTORY_FILE)
        if not path.exists():
            return {"version": 1, "profiles": {}}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VlessControlError(
                "Файл истории задержек VLESS повреждён; история не перезаписана."
            ) from exc
        if not isinstance(value, dict) or not isinstance(value.get("profiles"), dict):
            raise VlessControlError("Формат истории задержек VLESS не распознан.")
        value.setdefault("version", 1)
        return value

    def _save_delay_history(self, history):
        path = Path(DELAY_HISTORY_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(history, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        fd, temporary = tempfile.mkstemp(
            prefix=".vless-delay-history-", dir=str(path.parent)
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    @staticmethod
    def _delay_history_payload(profile_id, entry, now):
        entry = dict(entry or {})
        first_failed_at = entry.get("first_failed_at")
        unavailable_seconds = None
        if first_failed_at:
            started = _timestamp_datetime(first_failed_at)
            if started is not None:
                unavailable_seconds = max(0, int((now - started).total_seconds()))
        last_checked_at = entry.get("last_checked_at")
        return {
            "profile_id": int(profile_id),
            "delay_ms": entry.get("delay_ms"),
            "reachable": bool(
                entry.get("last_checked_at")
                and entry.get("delay_ms") is not None
                and not first_failed_at
            ),
            "first_failed_at": first_failed_at,
            "last_checked_at": last_checked_at,
            "last_success_at": entry.get("last_success_at"),
            "last_outage_started_at": entry.get("last_outage_started_at"),
            "last_recovered_at": entry.get("last_recovered_at"),
            "last_outage_duration_seconds": entry.get("last_outage_duration_seconds"),
            "consecutive_failures": int(entry.get("consecutive_failures") or 0),
            "unavailable_seconds": unavailable_seconds,
        }

    def _load_selection_history(self):
        try:
            raw = self.selection_history_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {
                "version": 1,
                "last_observation": None,
                "events": [],
                "profile_availability": {},
            }
        except OSError as exc:
            raise VlessControlError("Unable to read VLESS selection history") from exc
        try:
            document = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise VlessControlError(
                "VLESS selection history contains invalid JSON"
            ) from exc
        if not isinstance(document, dict):
            raise VlessControlError("VLESS selection history has an invalid structure")
        events = document.get("events", [])
        if not isinstance(events, list):
            raise VlessControlError("VLESS selection history events are invalid")
        last_observation = document.get("last_observation")
        if last_observation is not None and not isinstance(last_observation, dict):
            raise VlessControlError("VLESS selection history baseline is invalid")
        profile_availability = document.get("profile_availability", {})
        if not isinstance(profile_availability, dict):
            profile_availability = {}
        return {
            "version": 1,
            "last_observation": last_observation,
            "events": [event for event in events if isinstance(event, dict)][-200:],
            "profile_availability": {
                str(key): value
                for key, value in profile_availability.items()
                if isinstance(value, dict)
            },
        }

    def _save_selection_history(self, document):
        self.selection_history_file.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=".vless-selection-history-",
            dir=str(self.selection_history_file.parent),
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.selection_history_file)
            os.chmod(self.selection_history_file, 0o600)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _record_profile_availability(self, document, current, previous):
        """Track transitions in sing-box's successful URLTest history.

        Empty history is only considered a loss of result after this monitor has
        previously observed a successful sample for that profile. A first-ever
        empty history remains unknown. If every previously successful profile
        disappears from the same snapshot and no timestamped history remains,
        treat it as a possible sing-box history reset rather than asserting a
        simultaneous outage for every server.
        """
        states = document.setdefault("profile_availability", {})
        if not isinstance(states, dict):
            states = {}
            document["profile_availability"] = states

        previous_samples = (
            previous.get("profile_delays", {}) if isinstance(previous, dict) else {}
        )
        current_samples = current.get("profile_delays", {})
        if not isinstance(previous_samples, dict):
            previous_samples = {}
        if not isinstance(current_samples, dict):
            current_samples = {}

        def sample_parts(sample):
            if not isinstance(sample, dict):
                return None, None
            delay = sample.get("delay_ms")
            if isinstance(delay, bool) or not isinstance(delay, int) or delay <= 0:
                delay = None
            observed = sample.get("observed_at")
            if not isinstance(observed, str) or not observed.strip():
                observed = None
            return delay, observed

        previous_success_tags = {
            tag
            for tag, sample in previous_samples.items()
            if isinstance(tag, str)
            and re.fullmatch(r"vless-profile-[1-9][0-9]*", tag)
            and sample_parts(sample)[0] is not None
            and sample_parts(sample)[1] is not None
        }
        # Seed the new availability journal from the last persisted snapshot.
        # This is important when the patch is first installed: a profile may
        # disappear from history on the very first new observation, before the
        # new per-profile state has ever been written.
        for tag in previous_success_tags:
            match = re.fullmatch(r"vless-profile-([1-9][0-9]*)", tag)
            if not match:
                continue
            profile_id = int(match.group(1))
            key = str(profile_id)
            if key not in states:
                previous_delay, previous_at = sample_parts(previous_samples.get(tag))
                states[key] = {
                    "profile_id": profile_id,
                    "status": "reachable",
                    "reason": None,
                    "first_missing_at": None,
                    "last_success_at": previous_at,
                    "last_success_observed_at": previous_at,
                    "last_success_delay_ms": previous_delay,
                    "last_recovered_at": None,
                    "last_outage_duration_seconds": None,
                    "status_observed_at": previous.get("observed_at"),
                }
        current_success_tags = {
            tag
            for tag, sample in current_samples.items()
            if isinstance(tag, str)
            and re.fullmatch(r"vless-profile-[1-9][0-9]*", tag)
            and sample_parts(sample)[0] is not None
            and sample_parts(sample)[1] is not None
        }
        has_timestamped_history = any(
            sample_parts(sample)[1] is not None for sample in current_samples.values()
        )
        possible_history_reset = (
            bool(previous_success_tags)
            and not current_success_tags
            and not has_timestamped_history
        )
        monitor_observed_at = current.get("observed_at")
        if not isinstance(monitor_observed_at, str) or not monitor_observed_at:
            monitor_observed_at = _timestamp_iso(_utc_now())

        changed = False
        if possible_history_reset:
            for key, stored in list(states.items()):
                if not isinstance(stored, dict) or stored.get("status") != "reachable":
                    continue
                entry = dict(stored)
                entry["status"] = "unknown"
                entry["reason"] = "history_reset"
                entry["status_observed_at"] = monitor_observed_at
                entry["first_missing_at"] = None
                states[key] = entry
                changed = True

        for tag, sample in current_samples.items():
            match = (
                re.fullmatch(r"vless-profile-([1-9][0-9]*)", tag)
                if isinstance(tag, str)
                else None
            )
            if not match:
                continue
            profile_id = int(match.group(1))
            key = str(profile_id)
            delay, sample_at = sample_parts(sample)
            entry = dict(states.get(key) or {})
            entry.setdefault("profile_id", profile_id)
            entry.setdefault("status", "unknown")
            entry.setdefault("reason", "no_successful_history")

            last_success_at = entry.get("last_success_observed_at")
            last_success_dt = _timestamp_datetime(last_success_at)
            sample_dt = _timestamp_datetime(sample_at) if sample_at else None
            is_new_timestamped_sample = sample_dt is not None and (
                last_success_dt is None or sample_dt > last_success_dt
            )

            if delay is not None and (sample_at is None or is_new_timestamped_sample):
                recovered_at = sample_at or monitor_observed_at
                if entry.get("status") == "no_result" and entry.get("first_missing_at"):
                    missing_dt = _timestamp_datetime(entry.get("first_missing_at"))
                    recovered_dt = _timestamp_datetime(recovered_at)
                    if missing_dt is not None and recovered_dt is not None:
                        entry["last_outage_duration_seconds"] = max(
                            0, int((recovered_dt - missing_dt).total_seconds())
                        )
                    entry["last_recovered_at"] = recovered_at
                entry["status"] = "reachable"
                entry["reason"] = None
                entry["status_observed_at"] = monitor_observed_at
                entry["last_success_at"] = recovered_at
                entry["last_success_observed_at"] = recovered_at
                entry["last_success_delay_ms"] = delay
                entry["first_missing_at"] = None
                states[key] = entry
                changed = True
                continue

            # A timestamp with no positive delay is direct evidence of a failed
            # URLTest sample. Empty history is weaker: only a prior reachable
            # state lets us start a missing-result interval.
            if sample_at and delay is None and is_new_timestamped_sample:
                if (
                    entry.get("status") != "no_result"
                    or entry.get("first_missing_at") != sample_at
                ):
                    entry["status"] = "no_result"
                    entry["reason"] = "failed_urltest_sample"
                    entry["first_missing_at"] = (
                        entry.get("first_missing_at") or sample_at
                    )
                    entry["last_failure_observed_at"] = sample_at
                    entry["status_observed_at"] = monitor_observed_at
                    states[key] = entry
                    changed = True
                continue

            if (
                delay is None
                and sample_at is None
                and entry.get("status") == "reachable"
                and entry.get("last_success_observed_at")
            ):
                if possible_history_reset:
                    # The global reset branch above intentionally suppresses a
                    # false mass-outage claim. Wait for a new successful sample.
                    entry["status"] = "unknown"
                    entry["reason"] = "history_reset"
                    entry["status_observed_at"] = monitor_observed_at
                    entry["first_missing_at"] = None
                else:
                    entry["status"] = "no_result"
                    entry["reason"] = "successful_history_disappeared"
                    entry["first_missing_at"] = monitor_observed_at
                    entry["status_observed_at"] = monitor_observed_at
                states[key] = entry
                changed = True
            elif key not in states:
                states[key] = {
                    "profile_id": profile_id,
                    "status": "unknown",
                    "reason": "no_successful_history",
                    "first_missing_at": None,
                    "last_success_at": None,
                    "last_success_observed_at": None,
                    "last_success_delay_ms": None,
                    "last_recovered_at": None,
                    "last_outage_duration_seconds": None,
                    "status_observed_at": monitor_observed_at,
                }
                changed = True

        return changed

    @_serialized
    def record_selection_observation(self, snapshot):
        """Persist a selection change observed from the local sing-box Clash API.

        This method does not initiate delay tests or change the selected outbound.
        It intentionally labels causes as unknown unless the monitoring gap or
        selection-mode change itself is observable.
        """
        if not isinstance(snapshot, dict):
            raise VlessControlError("Invalid VLESS selection observation")
        current = dict(snapshot)
        mode = current.get("selection_mode")
        active = current.get("active_outbound")
        if mode not in ("auto", "manual", "unknown"):
            raise VlessControlError("Invalid VLESS selection mode")
        if active is not None and not re.fullmatch(
            r"vless-profile-[1-9][0-9]*", str(active)
        ):
            raise VlessControlError("Invalid active VLESS outbound tag")
        current.setdefault("observed_at", _timestamp_iso(_utc_now()))
        try:
            current["observed_at_epoch"] = float(
                current.get("observed_at_epoch") or _utc_now().timestamp()
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise VlessControlError("Invalid VLESS selection timestamp") from exc

        document = self._load_selection_history()
        bootstrapping = self._last_selection_snapshot is None
        previous = self._last_selection_snapshot
        if previous is None:
            previous = document.get("last_observation")

        availability_changed = self._record_profile_availability(
            document, current, previous if isinstance(previous, dict) else None
        )

        event = None
        changed = False
        if isinstance(previous, dict):
            previous_active = previous.get("active_outbound")
            previous_mode = previous.get("selection_mode")
            changed = previous_active != active or previous_mode != mode
            if changed and (previous_active or active):
                try:
                    gap_seconds = max(
                        0.0,
                        current["observed_at_epoch"]
                        - float(
                            previous.get("observed_at_epoch")
                            or current["observed_at_epoch"]
                        ),
                    )
                except (ValueError, TypeError, OverflowError):
                    gap_seconds = 999999.0

                if gap_seconds > 45:
                    reason = "observation_gap"
                    details = (
                        "Профиль изменился между наблюдениями после длительного перерыва "
                        "или перезапуска; точное время и первопричина неизвестны."
                    )
                elif previous_mode != mode:
                    reason = "selection_mode_changed"
                    details = (
                        "Наблюдалось изменение режима выбора; API не сообщает источник "
                        "действия."
                    )
                elif mode == "auto":
                    reason = "not_determined"
                    details = (
                        "Обнаружена смена активного участника URLTest. API sing-box не "
                        "раскрывает фактическую причину выбора; приведены последние "
                        "доступные измерения."
                    )
                else:
                    reason = "not_determined"
                    details = (
                        "Наблюдалась смена активного профиля в ручном режиме; источник "
                        "изменения по API не установлен."
                    )

                previous_sample = (previous.get("profile_delays") or {}).get(
                    previous_active, {}
                )
                active_sample = (current.get("profile_delays") or {}).get(active, {})
                if not isinstance(previous_sample, dict):
                    previous_sample = {}
                if not isinstance(active_sample, dict):
                    active_sample = {}
                event = {
                    "event_id": uuid.uuid4().hex,
                    "observed_at": current.get("observed_at"),
                    "previous_selection_mode": previous_mode,
                    "selection_mode": mode,
                    "previous_outbound": previous_active,
                    "active_outbound": active,
                    "previous_delay_ms": previous_sample.get("delay_ms"),
                    "active_delay_ms": active_sample.get("delay_ms"),
                    "previous_delay_observed_at": previous_sample.get("observed_at"),
                    "active_delay_observed_at": active_sample.get("observed_at"),
                    "urltest_interval": current.get("urltest_interval"),
                    "urltest_tolerance_ms": current.get("urltest_tolerance_ms"),
                    "reason": reason,
                    "reason_details": details,
                }
                event.update(
                    _selection_event_diagnostics(
                        previous_sample=previous_sample,
                        active_sample=active_sample,
                        observed_epoch=current.get("observed_at_epoch"),
                        interval=current.get("urltest_interval"),
                        tolerance=current.get("urltest_tolerance_ms"),
                        selection_mode=mode,
                        previous_mode=previous_mode,
                        reason=reason,
                        gap_seconds=gap_seconds,
                    )
                )
                document.setdefault("events", []).append(event)
                document["events"] = document["events"][-200:]

        # Persist a baseline on startup and on actual state changes only. This
        # avoids rewriting flash storage every 15-second monitor interval.
        if (
            bootstrapping
            or changed
            or availability_changed
            or document.get("last_observation") is None
        ):
            document["last_observation"] = current
            self._save_selection_history(document)
        self._last_selection_snapshot = current
        return event

    @_serialized
    def get_selection_history(self, monitor=None, current=None):
        document = self._load_selection_history()
        snapshot = current
        if snapshot is None:
            snapshot = self._last_selection_snapshot or document.get("last_observation")

        # Older persisted events predate freshness diagnostics. Enrich a response copy
        # from their already-stored timestamps; do not rewrite JSON history on flash.
        events = []
        for stored_event in document.get("events", [])[-200:]:
            event = dict(stored_event)
            if not event.get("diagnostic_status"):
                previous_sample = {
                    "delay_ms": event.get("previous_delay_ms"),
                    "observed_at": event.get("previous_delay_observed_at"),
                }
                active_sample = {
                    "delay_ms": event.get("active_delay_ms"),
                    "observed_at": event.get("active_delay_observed_at"),
                }
                event_epoch = _selection_timestamp_epoch(event.get("observed_at"))
                event.update(
                    _selection_event_diagnostics(
                        previous_sample=previous_sample,
                        active_sample=active_sample,
                        observed_epoch=event_epoch,
                        interval=event.get("urltest_interval"),
                        tolerance=event.get("urltest_tolerance_ms"),
                        selection_mode=event.get("selection_mode"),
                        previous_mode=event.get("previous_selection_mode"),
                        reason=event.get("reason"),
                        gap_seconds=None,
                    )
                )
                event["diagnostic_origin"] = "retrospective"
            else:
                event["diagnostic_origin"] = "recorded"
            events.append(event)

        availability = {}
        now = _utc_now()
        for profile_id, stored in document.get("profile_availability", {}).items():
            item = dict(stored)
            unavailable_seconds = None
            if item.get("status") == "no_result" and item.get("first_missing_at"):
                started = _timestamp_datetime(item.get("first_missing_at"))
                if started is not None:
                    unavailable_seconds = max(0, int((now - started).total_seconds()))
            item["unavailable_seconds"] = unavailable_seconds
            availability[str(profile_id)] = item

        return {
            "monitor": dict(monitor or {}),
            "current": snapshot,
            "events": events,
            "profile_availability": availability,
        }

    def _load_wan_fallback_state(self):
        state = {
            "active": False,
            "selection_mode": None,
            "fallback_started_at": None,
            "profile_counters": {},
            "probe_scope": None,
            "runtime_consecutive_failures": 0,
        }
        try:
            payload = json.loads(
                self.wan_fallback_state_file.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return state

        if not isinstance(payload, dict):
            return state

        state["active"] = payload.get("active") is True
        if state["active"]:
            selection_mode = payload.get("selection_mode")
            state["selection_mode"] = (
                selection_mode if selection_mode in ("auto", "manual") else None
            )
            started_at = payload.get("fallback_started_at")
            state["fallback_started_at"] = (
                started_at if isinstance(started_at, str) else None
            )
        return state

    def _save_wan_fallback_state(self, state):
        path = self.wan_fallback_state_file
        active = state.get("active") is True

        persisted = {
            "active": active,
            "selection_mode": (
                state.get("selection_mode")
                if active and state.get("selection_mode") in ("auto", "manual")
                else None
            ),
            "fallback_started_at": (
                state.get("fallback_started_at")
                if active and isinstance(state.get("fallback_started_at"), str)
                else None
            ),
        }
        content = (
            json.dumps(persisted, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )

        # No need to create an inactive marker file.
        if not active and not path.exists():
            return False

        # Avoid fsync and flash writes when durable state is unchanged.
        try:
            if path.read_text(encoding="utf-8") == content:
                if path.stat().st_mode & 0o777 != 0o600:
                    os.chmod(path, 0o600)
                return False
        except OSError:
            pass

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=".vless-wan-fallback-", dir=str(path.parent)
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, str(path))
            os.chmod(path, 0o600)
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return True

    def _probe_profiles(self, profiles):
        def check_one(profile):
            tag = "vless-profile-" + str(profile["id"])
            result = self._exec(
                [
                    "curl",
                    "-fsS",
                    "--max-time",
                    "7",
                    "--get",
                    "--data-urlencode",
                    "url=" + URLTEST_URL,
                    "--data-urlencode",
                    "timeout=5000",
                    "http://127.0.0.1:9090/proxies/" + tag + "/delay",
                ],
                timeout=8,
            )
            delay = None
            if result.returncode == 0:
                try:
                    value = json.loads(result.stdout or "{}").get("delay")
                    if (
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and value > 0
                    ):
                        delay = value
                except (ValueError, TypeError, AttributeError):
                    pass
            return {
                "profile_id": int(profile["id"]),
                "delay_ms": delay,
                "reachable": delay is not None,
            }

        if not profiles:
            return []
        with ThreadPoolExecutor(max_workers=min(16, len(profiles))) as pool:
            return list(pool.map(check_one, profiles))

    @_serialized
    def monitor_wan_fallback(self):
        store = self._load_store()
        settings = (
            store.get("settings") if isinstance(store.get("settings"), dict) else {}
        )
        state = self._load_wan_fallback_state()
        mode = self._read_mode()
        selection = (
            store.get("selection") if isinstance(store.get("selection"), dict) else {}
        )
        enabled_profiles = [
            profile
            for profile in store.get("profiles", [])
            if isinstance(profile, dict) and profile.get("enabled")
        ]

        if settings.get("wan_fallback_enabled") is not True:
            if state.get("active") and mode == "wan":
                try:
                    self.set_mode("vless", automatic_fallback=True)
                except Exception as exc:
                    return {"action": "restore-failed", "error": str(exc)[:180]}

            self._reset_wan_fallback_monitor_state()
            if state.get("active"):
                state["active"] = False
                state["selection_mode"] = None
                state["fallback_started_at"] = None
                self._save_wan_fallback_state(state)
            return {"action": "disabled", "active": False}

        if mode not in ("vless", "wan"):
            self._reset_wan_fallback_monitor_state()
            if state.get("active"):
                state["active"] = False
                state["selection_mode"] = None
                state["fallback_started_at"] = None
                self._save_wan_fallback_state(state)
            return {"action": "not-running", "active": False}

        runtime = None
        running = False

        if mode == "vless":
            running = self._running()
            if running:
                self._wan_fallback_runtime_failures = 0
                runtime = self._runtime_info(store)
                selection_mode = str(runtime.get("selection_mode") or "").lower()

                if state.get("active"):
                    state["active"] = False
                    state["selection_mode"] = None
                    state["fallback_started_at"] = None
                    self._save_wan_fallback_state(state)
                    self._reset_wan_fallback_monitor_state()
            else:
                selection_mode = str(selection.get("mode") or "auto").lower()
        else:
            if not state.get("active"):
                self._reset_wan_fallback_monitor_state()
                return {"action": "wan-selected-manually", "active": False}

            selection_mode = str(
                selection.get("mode") or state.get("selection_mode") or ""
            ).lower()

        # Resolve the real probe set before changing LAN routing.
        if selection_mode == "manual":
            if mode == "vless" and running:
                active = runtime.get("active_outbound")
                match = re.fullmatch(r"vless-profile-([1-9][0-9]*)", str(active or ""))
                profile_id = int(match.group(1)) if match else None
            else:
                try:
                    profile_id = int(selection.get("profile_id"))
                except (TypeError, ValueError):
                    profile_id = None

            profiles = [
                profile
                for profile in enabled_profiles
                if int(profile.get("id", -1)) == profile_id
            ]
        elif selection_mode == "auto":
            profiles = enabled_profiles
        else:
            self._wan_fallback_runtime_failures = 0
            return {
                "action": "selection-unknown",
                "active": state.get("active") is True,
            }

        if not profiles:
            self._wan_fallback_profile_counters = {}
            self._wan_fallback_probe_scope = None
            if mode == "vless" and not running:
                self._wan_fallback_runtime_failures = 0
            return {
                "action": "no-profiles",
                "active": state.get("active") is True,
            }

        # A stopped sing-box may trigger fallback only after two checks,
        # and only after confirming that the selected profile scope exists.
        if mode == "vless" and not running:
            self._wan_fallback_runtime_failures += 1
            if self._wan_fallback_runtime_failures < WAN_FALLBACK_FAILURE_THRESHOLD:
                return {"action": "runtime-unhealthy", "active": False}

            state["active"] = True
            state["selection_mode"] = selection_mode
            state["fallback_started_at"] = _timestamp_iso(_utc_now())
            self._save_wan_fallback_state(state)
            try:
                self.set_mode("wan", automatic_fallback=True)
            except Exception as exc:
                state["active"] = False
                state["selection_mode"] = None
                state["fallback_started_at"] = None
                self._save_wan_fallback_state(state)
                return {"action": "fallback-failed", "error": str(exc)[:180]}
            return {"action": "fallback-to-wan", "active": True}

        if mode == "wan" and not self._running():
            try:
                self.start()
            except Exception as exc:
                return {
                    "action": "recovery-probe-start-failed",
                    "active": True,
                    "error": str(exc)[:180],
                }

        probe_scope = (
            selection_mode
            + ":"
            + ",".join(str(profile.get("id")) for profile in profiles)
        )
        if self._wan_fallback_probe_scope != probe_scope:
            self._wan_fallback_profile_counters = {}
            self._wan_fallback_probe_scope = probe_scope

        try:
            results = self._probe_profiles(profiles)
        except Exception as exc:
            return {"action": "probe-failed", "error": str(exc)[:180]}
        if len(results) != len(profiles):
            return {"action": "probe-incomplete", "active": state.get("active") is True}

        counters = self._wan_fallback_profile_counters
        for result in results:
            key = str(result["profile_id"])
            counter = counters.get(key)
            if not isinstance(counter, dict):
                counter = {
                    "consecutive_failures": 0,
                    "consecutive_successes": 0,
                }

            if result["reachable"]:
                counter["consecutive_successes"] += 1
                counter["consecutive_failures"] = 0
            else:
                counter["consecutive_failures"] += 1
                counter["consecutive_successes"] = 0
            counters[key] = counter

        all_failed = all(
            counters[str(result["profile_id"])]["consecutive_failures"]
            >= WAN_FALLBACK_FAILURE_THRESHOLD
            for result in results
        ) and all(not result["reachable"] for result in results)

        any_recovered = any(
            counters[str(result["profile_id"])]["consecutive_successes"]
            >= WAN_FALLBACK_RECOVERY_THRESHOLD
            for result in results
        )

        if mode == "vless" and all_failed:
            state["active"] = True
            state["selection_mode"] = selection_mode
            state["fallback_started_at"] = _timestamp_iso(_utc_now())
            self._save_wan_fallback_state(state)
            try:
                self.set_mode("wan", automatic_fallback=True)
            except Exception as exc:
                state["active"] = False
                state["selection_mode"] = None
                state["fallback_started_at"] = None
                self._save_wan_fallback_state(state)
                return {"action": "fallback-failed", "error": str(exc)[:180]}
            return {"action": "fallback-to-wan", "active": True}

        if mode == "wan" and state.get("active") and any_recovered:
            try:
                self.set_mode("vless", automatic_fallback=True)
            except Exception as exc:
                return {"action": "recovery-failed", "error": str(exc)[:180]}

            state["active"] = False
            state["selection_mode"] = None
            state["fallback_started_at"] = None
            self._save_wan_fallback_state(state)
            self._reset_wan_fallback_monitor_state()
            return {"action": "recovered-to-vless", "active": False}

        return {
            "action": "checked",
            "active": state.get("active") is True,
            "reachable": sum(1 for result in results if result["reachable"]),
            "total": len(results),
        }

    @_serialized
    def get_delay_history(self):
        store = self._load_store()
        history = self._load_delay_history().get("profiles", {})
        now = _utc_now()
        results = []
        for profile in store.get("profiles", []):
            profile_id = int(profile.get("id"))
            entry = history.get(str(profile_id), {})
            if not entry.get("last_checked_at"):
                continue
            results.append(self._delay_history_payload(profile_id, entry, now))
        return {"results": results}

    @_serialized
    def test_delays(self):
        store = self._load_store()
        if not self._running():
            raise VlessControlError("Для проверки задержек сначала запустите sing-box.")
        enabled = [p for p in store.get("profiles", []) if p.get("enabled")]

        checked_results = self._probe_profiles(enabled)

        checked_at = _timestamp_iso(_utc_now())
        now = _timestamp_datetime(checked_at) or _utc_now()
        history_doc = self._load_delay_history()
        history = history_doc.setdefault("profiles", {})
        for result in checked_results:
            key = str(result["profile_id"])
            entry = dict(history.get(key) or {})
            if result["reachable"]:
                if entry.get("first_failed_at"):
                    failed_at = _timestamp_datetime(entry.get("first_failed_at"))
                    if failed_at is not None:
                        entry["last_outage_duration_seconds"] = max(
                            0, int((now - failed_at).total_seconds())
                        )
                    entry["last_outage_started_at"] = entry.get("first_failed_at")
                    entry["last_recovered_at"] = checked_at
                entry["first_failed_at"] = None
                entry["last_success_at"] = checked_at
                entry["consecutive_failures"] = 0
                entry["delay_ms"] = result["delay_ms"]
            else:
                if not entry.get("first_failed_at"):
                    entry["first_failed_at"] = checked_at
                    entry["last_outage_started_at"] = checked_at
                entry["consecutive_failures"] = (
                    int(entry.get("consecutive_failures") or 0) + 1
                )
                entry["delay_ms"] = None
            entry["profile_id"] = result["profile_id"]
            entry["last_checked_at"] = checked_at
            history[key] = entry

        self._save_delay_history(history_doc)
        results = [
            self._delay_history_payload(
                result["profile_id"], history.get(str(result["profile_id"]), {}), now
            )
            for result in checked_results
        ]
        return {
            "results": results,
            "reachable": sum(1 for item in results if item["reachable"]),
            "total": len(results),
        }

    @_serialized
    def set_mode(self, mode, *, automatic_fallback=False):
        mode = str(mode or "").strip().lower()
        if mode not in ("wan", "vpn", "vless"):
            raise VlessControlError("Неизвестный режим маршрутизации.")
        previous = self._read_mode()
        if mode == "vless":
            store = self._load_store()
            if not any(p.get("enabled") for p in store.get("profiles", [])):
                raise VlessControlError(
                    "Для VLESS сначала импортируйте и включите хотя бы один сервер."
                )
            if not self._running() or self._config_differs(store):
                # Switching LAN into VLESS must use the currently saved profile set,
                # not a stale running config left behind after import or edits.
                self.apply_config(start=True)
            check = self._exec(
                [str(SING_BOX), "check", "-c", str(self.config_file)], timeout=20
            )
            if check.returncode != 0:
                raise VlessControlError(
                    "Конфигурация sing-box не прошла проверку; LAN-маршрутизация не изменена."
                )
            command = ["/usr/bin/vpn-lan-vless-on"]
        elif mode == "vpn":
            command = ["/usr/bin/vpn-lan-on"]
        else:
            command = ["/usr/bin/vpn-lan-off"]
        try:
            self._checked(
                command, "Не удалось переключить режим маршрутизации", timeout=25
            )
            if self._read_mode() != mode:
                raise VlessControlError(
                    "Роутер не подтвердил выбранный режим маршрутизации."
                )
            if mode == "vless":
                deadline = time.time() + 4
                while time.time() < deadline:
                    info = self._runtime_info(self._load_store())
                    if info.get("lan_route_healthy"):
                        return info
                    time.sleep(0.25)
                raise VlessControlError(
                    "Режим VLESS выбран, но запуск sing-box или интерфейс maxvpn0 не подтверждён; выполнена попытка безопасного отката."
                )
        except Exception as exc:
            # A failed VLESS switch must not silently expose LAN through ordinary WAN.
            if mode == "vless":
                restore = {
                    "wan": "/usr/bin/vpn-lan-off",
                    "vpn": "/usr/bin/vpn-lan-on",
                    "vless": "/usr/bin/vpn-lan-vless-on",
                }.get(previous, "/usr/bin/vpn-lan-vless-on")
                self._exec([restore], timeout=20)
            elif previous in ("wan", "vpn", "vless") and previous != mode:
                restore = {
                    "wan": "/usr/bin/vpn-lan-off",
                    "vpn": "/usr/bin/vpn-lan-on",
                    "vless": "/usr/bin/vpn-lan-vless-on",
                }.get(previous)
                if restore:
                    self._exec([restore], timeout=20)
            raise VlessControlError(str(exc)) from exc
        if not automatic_fallback:
            self._reset_wan_fallback_monitor_state()
            state = self._load_wan_fallback_state()
            state["active"] = False
            state["selection_mode"] = None
            state["fallback_started_at"] = None
            state["profile_counters"] = {}
            state["probe_scope"] = None
            state["runtime_consecutive_failures"] = 0
            self._save_wan_fallback_state(state)
        return self._runtime_info(self._load_store())
