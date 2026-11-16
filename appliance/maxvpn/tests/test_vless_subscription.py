import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import vless_control
import vless_subscription
from vless_control import VlessControl, VlessControlError
from vless_subscription import SubscriptionError, parse_subscription, _validated_target


UUID = "123e4567-e89b-42d3-a456-426614174000"
PBK = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
LINK = (
    "vless://" + UUID + "@node.example.com:443?"
    "encryption=none&type=tcp&security=reality"
    "&sni=www.example.com&fp=chrome&pbk=" + PBK
    + "&sid=abcd&flow=xtls-rprx-vision#Sweden"
)


def test_plaintext_subscription():
    rows, errors = parse_subscription("#profile-title: Test\n" + LINK + "\n")
    assert rows == [LINK]
    assert errors == []


def test_base64_subscription():
    source = base64.b64encode((LINK + "\n").encode()).decode()
    rows, errors = parse_subscription(source)
    assert rows == [LINK]
    assert errors == []


def test_urlsafe_unpadded_base64_subscription():
    source = base64.urlsafe_b64encode((LINK + "\n").encode()).decode().rstrip("=")
    rows, errors = parse_subscription(source)
    assert rows == [LINK]
    assert errors == []


def test_skips_other_protocols_without_leaking_secrets():
    rows, errors = parse_subscription(
        "trojan://hidden-secret@server.example.com:443\n" + LINK + "\n"
    )
    assert rows == [LINK]
    assert errors == ["Неподдерживаемый протокол: trojan"]
    assert "hidden-secret" not in repr(errors)


def test_json_xray_outbounds():
    payload = {
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "vless", "tag": "proxy", "settings": {"vnext": []}},
        ]
    }
    rows, errors = parse_subscription(json.dumps(payload))
    assert len(rows) == 1
    assert '"protocol": "vless"' in rows[0]
    assert errors == []


def test_unsupported_format_clear_error():
    with pytest.raises(SubscriptionError, match="Base64|списком"):
        parse_subscription("proxies:\n  - name: Test\n    type: vless")


def test_oversized_content_is_rejected():
    with pytest.raises(SubscriptionError, match="Размер"):
        parse_subscription("x" * (vless_subscription.MAX_RESPONSE + 1))


@pytest.mark.parametrize("url", [
    "http://example.com/token",
    "https://user:pass@example.com/token",
    "https://example.com/token#fragment",
    "https://example.com/\r\nInjected: yes",
])
def test_untrusted_urls_rejected_before_request(url):
    with pytest.raises(SubscriptionError):
        _validated_target(url)


def test_private_ip_rejected():
    with pytest.raises(SubscriptionError, match="внутренней"):
        _validated_target("https://127.0.0.1:443/secret")


def test_dns_rebinding_protection(monkeypatch):
    monkeypatch.setattr(
        vless_subscription.socket, "getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("192.168.8.1", 443)),
        ],
    )
    with pytest.raises(SubscriptionError, match="внутренней"):
        _validated_target("https://sub.example.com/token")


def test_preview_is_read_only_and_sanitizes_credentials(tmp_path, monkeypatch):
    raw = LINK + "\nvmess://secret\n"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(
        vless_control, "fetch_subscription", lambda url, client="standard": (raw, digest)
    )
    control = VlessControl(profile_file=tmp_path / "profiles.json")
    preview = control.preview_subscription({
        "url": "https://sub.example.com/private", "client": "standard"
    })
    assert preview["compatible"] == 1
    assert preview["unsupported"] == 1
    assert preview["digest"] == digest
    assert UUID not in json.dumps(preview)
    assert "secret" not in json.dumps(preview)
    assert not (tmp_path / "profiles.json").exists()


def test_import_requires_digest_and_does_not_apply(tmp_path, monkeypatch):
    raw = LINK + "\n"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(
        vless_control, "fetch_subscription", lambda url, client="standard": (raw, digest)
    )
    monkeypatch.setattr(vless_control, "BACKUP_DIR", tmp_path / "backups")
    control = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "sing-box.json",
    )
    with pytest.raises(VlessControlError, match="предпросмотр"):
        control.import_subscription({"url": "https://example.com/t", "digest": "0" * 64})
    assert not (tmp_path / "profiles.json").exists()

    result = control.import_subscription({
        "url": "https://example.com/t", "client": "standard", "digest": digest
    })
    assert result["imported"] == 1
    assert (tmp_path / "profiles.json").exists()
    assert not (tmp_path / "sing-box.json").exists()
    again = control.import_subscription({
        "url": "https://example.com/t", "client": "standard", "digest": digest
    })
    assert again["imported"] == 0
    assert again["updated"] == 1
    assert len(json.loads((tmp_path / "profiles.json").read_text())["profiles"]) == 1


def test_unsupported_transport_skipped_without_write(tmp_path, monkeypatch):
    raw = LINK.replace("type=tcp", "type=xhttp")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(
        vless_control, "fetch_subscription", lambda url, client="standard": (raw, digest)
    )
    control = VlessControl(profile_file=tmp_path / "profiles.json")
    preview = control.preview_subscription({"url": "https://example.com/t"})
    assert preview["compatible"] == 0
    assert preview["unsupported"] == 1
    with pytest.raises(VlessControlError, match="нет серверов"):
        control.import_subscription({"url": "https://example.com/t", "digest": digest})
    assert not (tmp_path / "profiles.json").exists()


def test_identity_distinguishes_reality_fingerprint():
    original = vless_control._parse_vless_uri(LINK)
    firefox = vless_control._parse_vless_uri(LINK.replace("fp=chrome", "fp=firefox"))
    assert vless_control._identity(original) != vless_control._identity(firefox)


def test_identity_distinguishes_reality_from_plain_vless():
    original = vless_control._parse_vless_uri(LINK)
    plain = vless_control._parse_vless_uri(
        LINK.replace("security=reality", "security=none")
    )
    assert vless_control._identity(original) != vless_control._identity(plain)


def test_subscription_same_connection_different_titles_deduplicates(
    tmp_path, monkeypatch
):
    second = LINK.replace("#Sweden", "#Fast%20Sweden")
    raw = LINK + "\n" + second + "\n"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(
        vless_control, "fetch_subscription",
        lambda url, client="standard": (raw, digest),
    )
    monkeypatch.setattr(vless_control, "BACKUP_DIR", tmp_path / "backups")
    manager = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "sing-box.json",
    )
    preview = manager.preview_subscription({"url": "https://example.com/sub"})
    assert preview["compatible"] == 2
    assert preview["unique_connections"] == 1
    assert preview["duplicate_aliases"] == 1
    result = manager.import_subscription({
        "url": "https://example.com/sub", "digest": digest,
    })
    assert result["imported"] == 1
    assert result["updated"] == 1
    assert len(manager._load_store()["profiles"]) == 1


def test_subscription_distinct_fingerprints_are_not_merged(tmp_path, monkeypatch):
    other = LINK.replace("fp=chrome", "fp=firefox").replace("#Sweden", "#Sweden%202")
    raw = LINK + "\n" + other + "\n"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    monkeypatch.setattr(
        vless_control, "fetch_subscription",
        lambda url, client="standard": (raw, digest),
    )
    monkeypatch.setattr(vless_control, "BACKUP_DIR", tmp_path / "backups")
    manager = VlessControl(
        profile_file=tmp_path / "profiles.json",
        config_file=tmp_path / "sing-box.json",
    )
    preview = manager.preview_subscription({"url": "https://example.com/sub"})
    assert preview["compatible"] == 2
    assert preview["unique_connections"] == 2
    assert preview["duplicate_aliases"] == 0
    result = manager.import_subscription({
        "url": "https://example.com/sub", "digest": digest,
    })
    assert result["imported"] == 2
    assert result["updated"] == 0
    assert len(manager._load_store()["profiles"]) == 2
