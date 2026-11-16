"""Safe, bounded download and decoding of VLESS subscription URLs.

No shell execution, no redirects to other hosts, and HTTPS connections are
pinned to globally routable DNS answers to prevent DNS rebinding/SSRF.
Only server entries are extracted; no routing rules from subscriptions are run.
"""
import base64
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit

MAX_RESPONSE = 2 * 1024 * 1024
MAX_ENTRIES = 500
USER_AGENTS = {"standard": "v2rayN/7.0", "happ": "Happ/2.0"}


class SubscriptionError(ValueError):
    pass


def _validated_target(url):
    if not isinstance(url, str) or len(url) > 4096 or not url.strip():
        raise SubscriptionError("Некорректный адрес подписки.")
    if any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise SubscriptionError("Адрес подписки содержит управляющие символы.")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port or 443
    except ValueError as exc:
        raise SubscriptionError("Некорректный URL подписки.") from exc
    if (
        parsed.scheme.lower() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not 1 <= port <= 65535
    ):
        raise SubscriptionError("Подписка должна быть HTTPS URL без учётных данных и фрагмента.")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
        raise SubscriptionError("Некорректное доменное имя подписки.")
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise SubscriptionError("Не удалось разрешить адрес подписки.") from exc
    addresses = list(dict.fromkeys(item[4][0] for item in results))
    if not addresses or len(addresses) > 32:
        raise SubscriptionError("Не удалось проверить DNS адрес подписки.")
    if any(not ipaddress.ip_address(addr).is_global for addr in addresses):
        raise SubscriptionError("Запрещён адрес подписки во внутренней сети.")
    return parsed, host, port, addresses


def _request_once(url, user_agent):
    parsed, host, port, addresses = _validated_target(url)
    target = parsed.path or "/"
    if parsed.query:
        target += "?" + parsed.query
    host_header = host if port == 443 else host + ":" + str(port)
    request = (
        "GET " + target + " HTTP/1.1\r\n"
        + "Host: " + host_header + "\r\n"
        + "User-Agent: " + user_agent + "\r\n"
        + "Accept: text/plain, application/json\r\n"
        + "Accept-Encoding: identity\r\n"
        + "Connection: close\r\n\r\n"
    ).encode("utf-8")
    context = ssl.create_default_context()
    last_error = None
    for addr in addresses[:4]:
        sock = None
        tls_socket = None
        response = None
        try:
            sock = socket.create_connection((addr, port), timeout=7)
            tls_socket = context.wrap_socket(sock, server_hostname=host)
            sock = None  # ownership transferred to the TLS socket
            tls_socket.settimeout(7)
            tls_socket.sendall(request)
            response = http.client.HTTPResponse(tls_socket)
            response.begin()
            status = response.status
            if status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                return status, b"", location
            if status != 200:
                raise SubscriptionError("Сервер подписки вернул HTTP " + str(status) + ".")
            if (response.getheader("Content-Encoding") or "identity").lower() != "identity":
                raise SubscriptionError("Сервер подписки вернул неподдерживаемое сжатие.")
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise SubscriptionError("Размер подписки превышает 2 МиБ.")
            return status, raw, None
        except SubscriptionError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
        finally:
            if response is not None:
                response.close()
            if tls_socket is not None:
                tls_socket.close()
            if sock is not None:
                sock.close()
    raise SubscriptionError("Не удалось безопасно загрузить подписку по HTTPS.") from last_error


def fetch_subscription(url, client="standard"):
    """Returns (UTF-8 subscription text, SHA256 of raw response)."""
    if client not in USER_AGENTS:
        raise SubscriptionError("Неизвестный тип клиента подписки.")
    initial_host = _validated_target(url)[1].lower()
    current = url
    for _ in range(3):
        status, raw, location = _request_once(current, USER_AGENTS[client])
        if status == 200:
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise SubscriptionError("Подписка не содержит UTF-8 текст.") from exc
            return text, hashlib.sha256(raw).hexdigest()
        if not location:
            raise SubscriptionError("Сервер перенаправил подписку без адреса.")
        next_url = urljoin(current, location)
        if _validated_target(next_url)[1].lower() != initial_host:
            raise SubscriptionError("Перенаправление подписки на другой домен запрещено.")
        current = next_url
    raise SubscriptionError("Слишком много перенаправлений подписки.")


def _json_entries(document):
    """Extract VLESS URIs or single Xray VLESS outbounds from JSON."""
    entries = []
    skipped = []
    if isinstance(document, dict) and isinstance(document.get("outbounds"), list):
        for outbound in document["outbounds"]:
            if not isinstance(outbound, dict):
                continue
            if outbound.get("protocol") == "vless":
                entries.append(json.dumps({
                    "outbounds": [outbound],
                    "remarks": outbound.get("tag", "VLESS"),
                }, ensure_ascii=False))
            elif outbound.get("type") == "vless":
                skipped.append("sing-box JSON outbound: требуется отдельный конвертер")
        return entries, skipped
    if isinstance(document, dict):
        for key in ("servers", "nodes", "configs", "proxies", "profiles", "data"):
            if isinstance(document.get(key), list):
                document = document[key]
                break
    if isinstance(document, list):
        for item in document:
            if isinstance(item, str):
                entries.append(item.strip())
            elif isinstance(item, dict):
                source = item.get("uri") or item.get("url") or item.get("link")
                if isinstance(source, str):
                    entries.append(source.strip())
                elif item.get("protocol") == "vless":
                    entries.append(json.dumps({"outbounds": [item]}, ensure_ascii=False))
                else:
                    skipped.append("JSON-узел с неподдерживаемой структурой")
        return entries, skipped
    raise SubscriptionError("Формат JSON подписки не распознан.")


def parse_subscription(text):
    """Returns (candidate sources, sanitized unsupported-format reasons)."""
    if not isinstance(text, str) or len(text) > MAX_RESPONSE:
        raise SubscriptionError("Размер подписки превышает установленный предел.")
    content = text.strip()
    if not content:
        raise SubscriptionError("Подписка пуста.")
    if content[0] in "[{":
        try:
            return _json_entries(json.loads(content))
        except json.JSONDecodeError as exc:
            raise SubscriptionError("Некорректный JSON подписки.") from exc
    if "://" not in content:
        compact = "".join(content.split())
        try:
            raw = base64.b64decode(compact + "=" * (-len(compact) % 4),
                                   altchars=b"-_", validate=True)
            content = raw.decode("utf-8-sig").strip()
        except (ValueError, UnicodeError, base64.binascii.Error) as exc:
            raise SubscriptionError("Подписка не является списком URI или Base64.") from exc
        if not content:
            raise SubscriptionError("Декодированная подписка пуста.")
        if content[0] in "[{":
            try:
                return _json_entries(json.loads(content))
            except json.JSONDecodeError as exc:
                raise SubscriptionError("Некорректный JSON подписки.") from exc
    candidates = []
    skipped = []
    for line in content.splitlines():
        source = line.strip()
        if not source or source.startswith("#"):
            continue
        scheme = source.split("://", 1)[0].lower() if "://" in source else ""
        if scheme == "vless":
            candidates.append(source)
        elif scheme in ("vmess", "trojan", "ss", "socks", "hysteria2", "tuic", "happ"):
            skipped.append("Неподдерживаемый протокол: " + scheme)
        elif scheme:
            skipped.append("Неподдерживаемая схема подключения")
    if len(candidates) + len(skipped) > MAX_ENTRIES:
        raise SubscriptionError("В подписке слишком много серверов.")
    if not candidates and not skipped:
        raise SubscriptionError("Не найдены ссылки серверов. Возможно, это Clash YAML или другой формат.")
    return candidates, skipped
