import json
import threading
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch
import time

with patch.object(Path, "mkdir"):
    from appliance.maxvpn import server as appliance

CLIENT = "192.168.8.231"


def post_json(path, payload):
    server = appliance.ThreadingHTTPServer(("127.0.0.1", 0), appliance.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=3)
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        raw = response.read()
        result = json.loads(raw.decode("utf-8")) if raw else {}
        return response.status, result
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def add_session(
    monkeypatch, *, domain="2gis.ru", token="a" * 32, running=False, resources=None
):
    session = {
        "domain": domain,
        "requested_client_ip": CLIENT,
        "started_at": time.time() - 20,
        "expires_at": time.time() + 20 if running else time.time() - 1,
        "cursor": {"inode": 0, "offset": 0},
        "parser_state": {"transactions": {}, "selected_client_ip": CLIENT},
        "observed_resources": (
            resources
            if resources is not None
            else {
                "jam.api.2gis.com": {
                    "hostname": "jam.api.2gis.com",
                    "ips": ["91.236.49.1"],
                    "queries": 1,
                }
            }
        ),
    }
    monkeypatch.setitem(appliance.DIAGNOSTICS, token, session)
    monkeypatch.setattr(appliance, "_diagnostic_direct_ips", lambda: set())
    monkeypatch.setattr(appliance, "_diagnostic_domain_rules", lambda: [])
    return token, session


def test_invalid_diagnostic_token_is_rejected(monkeypatch):
    monkeypatch.delitem(appliance.DIAGNOSTICS, "missing-token", raising=False)
    try:
        appliance._diagnostic_validate_direct_candidate(
            "missing-token", "jam.api.2gis.com"
        )
    except ValueError as exc:
        assert "session not found" in str(exc)
    else:
        raise AssertionError("invalid token was accepted")


def test_running_session_cannot_create_direct_rule(monkeypatch):
    token, _ = add_session(monkeypatch, running=True)
    try:
        appliance._diagnostic_validate_direct_candidate(token, "jam.api.2gis.com")
    except ValueError as exc:
        assert "still running" in str(exc)
    else:
        raise AssertionError("running diagnostic session was accepted")


def test_unrelated_hostname_is_rejected_even_if_observed(monkeypatch):
    resources = {
        "cdn.example.net": {
            "hostname": "cdn.example.net",
            "ips": ["203.0.113.8"],
            "queries": 1,
        }
    }
    token, _ = add_session(monkeypatch, resources=resources)
    try:
        appliance._diagnostic_validate_direct_candidate(token, "cdn.example.net")
    except ValueError as exc:
        assert "not related" in str(exc)
    else:
        raise AssertionError("unrelated hostname was accepted")


def test_related_but_unobserved_hostname_is_rejected(monkeypatch):
    token, _ = add_session(monkeypatch)
    try:
        appliance._diagnostic_validate_direct_candidate(token, "media.2gis.ru")
    except ValueError as exc:
        assert "not observed" in str(exc)
    else:
        raise AssertionError("unobserved hostname was accepted")


def test_candidate_without_ipv4_is_rejected(monkeypatch):
    resources = {
        "jam.api.2gis.com": {"hostname": "jam.api.2gis.com", "ips": [], "queries": 1}
    }
    token, _ = add_session(monkeypatch, resources=resources)
    try:
        appliance._diagnostic_validate_direct_candidate(token, "jam.api.2gis.com")
    except ValueError as exc:
        assert "no observed IPv4" in str(exc)
    else:
        raise AssertionError("hostname without IPv4 was accepted")


def test_any_existing_direct_ip_makes_candidate_ambiguous(monkeypatch):
    token, _ = add_session(monkeypatch)
    monkeypatch.setattr(appliance, "_diagnostic_direct_ips", lambda: {"91.236.49.1"})
    try:
        appliance._diagnostic_validate_direct_candidate(token, "jam.api.2gis.com")
    except ValueError as exc:
        assert "ambiguous DIRECT" in str(exc)
    else:
        raise AssertionError("ambiguous route was accepted")


def test_active_covering_domain_rule_rejects_candidate(monkeypatch):
    token, _ = add_session(monkeypatch)
    monkeypatch.setattr(appliance, "_diagnostic_domain_rules", lambda: ["2gis.com"])
    try:
        appliance._diagnostic_validate_direct_candidate(token, "jam.api.2gis.com")
    except ValueError as exc:
        assert "already covered" in str(exc)
    else:
        raise AssertionError("already-covered hostname was accepted")


def test_observed_brand_alias_candidate_is_accepted(monkeypatch):
    token, session = add_session(monkeypatch)
    hostname, returned_session = appliance._diagnostic_validate_direct_candidate(
        token, "jam.api.2gis.com"
    )
    assert hostname == "jam.api.2gis.com"
    assert returned_session is session


def test_same_site_hostname_is_accepted(monkeypatch):
    resources = {
        "static.example.org": {
            "hostname": "static.example.org",
            "ips": ["203.0.113.10"],
            "queries": 2,
        }
    }
    token, _ = add_session(monkeypatch, domain="example.org", resources=resources)
    hostname, _ = appliance._diagnostic_validate_direct_candidate(
        token, "static.example.org"
    )
    assert hostname == "static.example.org"


def test_diagnostic_rule_creation_uses_test_database_and_does_not_apply_routes(
    monkeypatch, tmp_path
):
    token, _ = add_session(monkeypatch)
    monkeypatch.setattr(appliance, "DB", tmp_path / "test-maxvpn.db")
    monkeypatch.setattr(
        appliance,
        "apply_routing",
        lambda: (_ for _ in ()).throw(AssertionError("must not apply")),
    )

    created = appliance._diagnostic_create_direct_rule(token, "jam.api.2gis.com")
    assert created["target_type"] == "domain"
    assert created["target"] == "jam.api.2gis.com"
    assert created["action"] == "direct"
    assert created["enabled"] is True
    assert created["comment"] == "Диагностика: 2gis.ru"

    c = appliance.db()
    try:
        rows = c.execute("SELECT target FROM rules").fetchall()
        assert [row["target"] for row in rows] == ["jam.api.2gis.com"]
    finally:
        c.close()


def test_manual_rule_endpoint_and_generic_creation_path_remain_present():
    source = Path(appliance.__file__).read_text(encoding="utf-8")
    assert 'if path == "/api/appliance/v1/routing/rules":' in source
    assert 'target = validate_target(target_type, data.get("target", ""))' in source
    assert "_diagnostic_create_direct_rule(" in source


def test_diagnostic_direct_candidates_are_not_selectable_until_finished():
    root = Path(__file__).resolve().parents[3]
    html = (root / "appliance/maxvpn/index.html").read_text(encoding="utf-8")
    server = (root / "appliance/maxvpn/server.py").read_text(encoding="utf-8")

    assert "const checked=!data.running && x.candidate_eligible===true;" in html
    assert (
        "!data.running && resources.some(x=>x.candidate_eligible===true)?'':'disabled'"
        in html
    )
    assert (
        'item["candidate_eligible"] = bool(finished and item["candidate_for_direct"])'
        in server
    )
    assert 'if time.time() < float(session.get("expires_at", 0)):' in server
    assert (
        'if not _diagnostic_candidate_related(hostname, session.get("domain", "")):'
        in server
    )


def test_http_diagnostic_direct_endpoint_returns_created_then_conflict(
    monkeypatch, tmp_path
):
    token, _ = add_session(monkeypatch)
    monkeypatch.setattr(appliance, "DB", tmp_path / "http-diagnostic.db")
    monkeypatch.setattr(
        appliance,
        "apply_routing",
        lambda: (_ for _ in ()).throw(AssertionError("routes must not be applied")),
    )
    path = f"/api/appliance/v1/routing/diagnostics/{token}/direct"
    payload = {"target": "jam.api.2gis.com"}

    status, result = post_json(path, payload)
    assert status == 201
    assert result["target"] == "jam.api.2gis.com"
    assert result["action"] == "direct"

    status, result = post_json(path, payload)
    assert status == 409
    assert result["error"] == "rule already exists"

    connection = appliance.db()
    try:
        rows = connection.execute("SELECT target FROM rules").fetchall()
        assert [row["target"] for row in rows] == ["jam.api.2gis.com"]
    finally:
        connection.close()


def test_http_diagnostic_direct_endpoint_returns_422_for_invalid_token(monkeypatch):
    token = "b" * 32
    monkeypatch.delitem(appliance.DIAGNOSTICS, token, raising=False)

    status, result = post_json(
        f"/api/appliance/v1/routing/diagnostics/{token}/direct",
        {"target": "jam.api.2gis.com"},
    )

    assert status == 422
    assert "session not found" in result["error"]


def test_http_manual_rule_endpoint_still_creates_rule(monkeypatch, tmp_path):
    monkeypatch.setattr(appliance, "DB", tmp_path / "http-manual.db")
    monkeypatch.setattr(
        appliance,
        "apply_routing",
        lambda: (_ for _ in ()).throw(AssertionError("routes must not be applied")),
    )

    status, result = post_json(
        "/api/appliance/v1/routing/rules",
        {
            "target_type": "domain",
            "target": "manual.example.org",
            "comment": "manual test",
        },
    )

    assert status == 201
    assert result["target"] == "manual.example.org"
    assert result["comment"] == "manual test"
