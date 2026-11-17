#!/usr/bin/env python3
"""Read-only privacy-preserving VLESS subscription format inspection.

Usage:
  python3 scripts/inspect_vless_subscription.py --client happ

The URL is requested through a hidden terminal prompt; never put it in a CLI
argument, shell history, issue, log or chat. This helper prints only aggregate
protocol/transport counts and compatibility reasons, never credentials, hostnames
or individual server URIs.
"""
import argparse
from collections import Counter
from getpass import getpass
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "appliance" / "maxvpn"))

from vless_subscription import SubscriptionError, fetch_subscription, parse_subscription  # noqa: E402
from vless_control import _parse_happ_json, _parse_vless_uri  # noqa: E402

KNOWN_TRANSPORTS = {"tcp", "ws", "grpc", "xhttp", "httpupgrade", "quic", "http", "h2", "kcp"}


def _safe_transport(name):
    value = str(name or "tcp").lower()
    return value if value in KNOWN_TRANSPORTS else "other"


def describe(text):
    """Aggregate compatibility metadata; never return addresses or credentials."""
    candidates, skipped = parse_subscription(text)
    transports = Counter()
    security = Counter()
    incompatible = Counter()
    supported = 0
    for source in candidates:
        if source.startswith("vless://"):
            parts = urlsplit(source)
            query = parse_qs(parts.query)
            network = query.get("type", ["tcp"])[0]
            sec = query.get("security", ["none"])[0]
        else:
            try:
                document = json.loads(source)
                outbound = next(
                    item for item in document["outbounds"]
                    if item.get("protocol") == "vless"
                )
                stream = outbound.get("streamSettings") or {}
                network = stream.get("network") or "tcp"
                sec = stream.get("security") or "none"
            except (KeyError, ValueError, TypeError, StopIteration):
                network = "unknown"
                sec = "unknown"
        transports[_safe_transport(network)] += 1
        security[str(sec).lower() if str(sec).lower() in ("none", "tls", "reality") else "other"] += 1
        try:
            if source.startswith("vless://"):
                _parse_vless_uri(source)
            else:
                _parse_happ_json(source)
            supported += 1
        except (ValueError, KeyError, TypeError) as exc:
            message = str(exc).lower()
            if "transport" in message or "tcp" in message:
                incompatible["unsupported_transport"] += 1
            elif "tls" in message or "reality" in message:
                incompatible["unsupported_tls_or_reality"] += 1
            elif "flow" in message:
                incompatible["unsupported_flow"] += 1
            else:
                incompatible["invalid_profile"] += 1
    return {
        "total_recognized_vless": len(candidates),
        "compatible_vless": supported,
        "other_protocol_or_format": len(skipped),
        "transports": dict(sorted(transports.items())),
        "security": dict(sorted(security.items())),
        "incompatible_reasons": dict(sorted(incompatible.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", choices=["standard", "happ"], default="happ",
                        help="Subscription request User-Agent; default: happ")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Run interactively to avoid exposing the subscription URL.")
    url = getpass("Вставь секретную HTTPS-ссылку подписки (не отображается): ")
    try:
        text, _digest = fetch_subscription(url, client=args.client)
        summary = describe(text)
    except (SubscriptionError, ValueError, TypeError) as exc:
        # The original error is deliberately not printed: network exceptions
        # can contain a URL or other sensitive details on some platforms.
        print("Подписка не разобрана: ошибка загрузки или неизвестный формат.")
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
