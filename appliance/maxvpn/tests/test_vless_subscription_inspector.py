import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from scripts.inspect_vless_subscription import describe  # noqa: E402

UUID = "123e4567-e89b-42d3-a456-426614174000"
PBK = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
URL = "vless://" + UUID + "@private-host.example.com:443?type=tcp&security=reality&sni=example.com&pbk=" + PBK


def test_inspector_produces_only_aggregate_counts():
    result = describe(URL + "\n")
    assert result["total_recognized_vless"] == 1
    assert result["compatible_vless"] == 1
    assert result["transports"] == {"tcp": 1}
    assert result["security"] == {"reality": 1}
    as_text = json.dumps(result)
    assert UUID not in as_text
    assert "private-host.example.com" not in as_text
    assert PBK not in as_text


def test_inspector_distinguishes_incompatible_transport():
    result = describe(URL.replace("type=tcp", "type=xhttp") + "\n")
    assert result["total_recognized_vless"] == 1
    assert result["compatible_vless"] == 0
    assert result["transports"] == {"xhttp": 1}
    assert result["incompatible_reasons"] == {"unsupported_transport": 1}


def test_inspector_reports_unsupported_protocol_without_leaking_secrets():
    result = describe("trojan://private-password@example.com:443\n" + URL)
    assert result["other_protocol_or_format"] == 1
    assert "private-password" not in json.dumps(result)
