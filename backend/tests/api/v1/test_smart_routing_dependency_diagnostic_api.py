from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.v1.smart_routing_dependency_diagnostic import (
    get_group_repository,
    get_repository,
    get_runtime_executor,
    get_session_service,
)
from app.auth.dependencies import get_current_user
from app.database.dependencies import get_db
from app.main import app
from app.models.user import User

client = TestClient(app)


def make_user() -> User:
    return User(
        id=42,
        email="user@example.com",
        password_hash="hash",
        role="user",
    )


def test_start_dependency_diagnostic_requires_authentication():
    response = client.post(
        "/api/v1/smart-routing/dependency-diagnostic/start",
        json={
            "site_domain": "2gis.ru",
            "client_ip": "192.168.31.100",
            "duration_seconds": 30,
        },
    )

    assert response.status_code == 401


def test_start_dependency_diagnostic_returns_session():
    current_user = make_user()

    service = Mock()
    service.start.return_value = {
        "token": "abc123",
        "site_domain": "2gis.ru",
        "client_ip": "192.168.31.100",
        "started_at": 1000,
        "expires_at": 1030,
        "running": True,
        "remaining_seconds": 30,
    }

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service

    try:
        response = client.post(
            "/api/v1/smart-routing/dependency-diagnostic/start",
            json={
                "site_domain": "2GIS.RU.",
                "client_ip": "192.168.31.100",
                "duration_seconds": 30,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["token"] == "abc123"
    assert response.json()["site_domain"] == "2gis.ru"

    service.start.assert_called_once_with(
        site_domain="2GIS.RU.",
        client_ip="192.168.31.100",
        duration_seconds=30,
    )


def test_start_dependency_diagnostic_resolves_ip_from_trusted_frontend_proxy():
    current_user = make_user()
    service = Mock()
    service.start.return_value = {
        "token": "auto-ip",
        "site_domain": "2gis.ru",
        "client_ip": "192.168.8.231",
        "started_at": 1000,
        "expires_at": 1030,
        "running": True,
        "remaining_seconds": 30,
    }
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service

    try:
        proxy_client = TestClient(app, client=("172.18.0.4", 54321))
        response = proxy_client.post(
            "/api/v1/smart-routing/dependency-diagnostic/start",
            json={"site_domain": "2gis.ru", "duration_seconds": 30},
            headers={"X-Real-IP": "192.168.8.231"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["client_ip"] == "192.168.8.231"
    service.start.assert_called_once_with(
        site_domain="2gis.ru",
        client_ip="192.168.8.231",
        duration_seconds=30,
    )


def test_start_dependency_diagnostic_does_not_trust_forwarded_ip_from_public_peer():
    current_user = make_user()
    service = Mock()
    service.start.return_value = {
        "token": "peer-ip",
        "site_domain": "2gis.ru",
        "client_ip": "8.8.8.8",
        "started_at": 1000,
        "expires_at": 1030,
        "running": True,
        "remaining_seconds": 30,
    }
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service

    try:
        public_client = TestClient(app, client=("8.8.8.8", 54321))
        response = public_client.post(
            "/api/v1/smart-routing/dependency-diagnostic/start",
            json={"site_domain": "2gis.ru", "duration_seconds": 30},
            headers={"X-Real-IP": "192.168.8.231"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "IP клиента" in response.json()["detail"]
    service.start.assert_not_called()


def test_start_dependency_diagnostic_does_not_trust_x_real_ip_from_other_private_peer():
    current_user = make_user()
    service = Mock()
    service.start.return_value = {
        "token": "private-peer-ip",
        "site_domain": "2gis.ru",
        "client_ip": "172.18.0.22",
        "started_at": 1000,
        "expires_at": 1030,
        "running": True,
        "remaining_seconds": 30,
    }
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service

    try:
        private_client = TestClient(app, client=("172.18.0.22", 54321))
        response = private_client.post(
            "/api/v1/smart-routing/dependency-diagnostic/start",
            json={"site_domain": "2gis.ru", "duration_seconds": 30},
            headers={"X-Real-IP": "192.168.8.231"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "IP клиента" in response.json()["detail"]
    service.start.assert_not_called()


def test_start_dependency_diagnostic_validates_duration():
    current_user = make_user()

    app.dependency_overrides[get_current_user] = lambda: current_user

    try:
        response = client.post(
            "/api/v1/smart-routing/dependency-diagnostic/start",
            json={
                "site_domain": "2gis.ru",
                "client_ip": "192.168.31.100",
                "duration_seconds": 10,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_poll_dependency_diagnostic_returns_group_result():
    current_user = make_user()

    service = Mock()
    service.poll.return_value = (
        {
            "token": "abc123",
            "site_domain": "2gis.ru",
            "client_ip": "192.168.31.100",
            "running": False,
            "remaining_seconds": 0,
            "summary": {
                "observed": 2,
                "direct": 1,
                "vpn": 1,
                "partial": 0,
                "unknown": 0,
                "uncovered": 1,
            },
            "resources": [
                {
                    "hostname": "maps.2gis.com",
                    "ips": ["91.236.49.2"],
                    "cname_chain": [
                        "tile3.maps.2gis.com",
                        "tile0.maps.2gis.com",
                    ],
                    "query_count": 2,
                    "relation": "external",
                    "routing": "direct",
                    "covered_by_rule": True,
                    "rule_domain": "maps.2gis.com",
                    "candidate_for_direct": False,
                    "selection_allowed": False,
                    "category": "external_candidate",
                    "category_detail": "Домен пространства бренда (.2gis.com)",
                    "brand_alias": True,
                    "synthetic": False,
                    "observed_hostnames": ["maps.2gis.com"],
                    "relevance": "likely",
                    "relevance_score": 70,
                    "dependency_reasons": [],
                    "related_hostnames": [],
                    "recommended_for_direct": False,
                },
                {
                    "hostname": "photo.2gis.com",
                    "ips": ["91.240.170.190"],
                    "cname_chain": [
                        "photo.2gis.com",
                    ],
                    "query_count": 1,
                    "relation": "external",
                    "routing": "vpn",
                    "covered_by_rule": False,
                    "rule_domain": None,
                    "candidate_for_direct": True,
                    "selection_allowed": True,
                    "category": "external_candidate",
                    "category_detail": "Домен пространства бренда (.2gis.com)",
                    "brand_alias": True,
                    "synthetic": False,
                    "observed_hostnames": ["photo.2gis.com"],
                    "relevance": "likely",
                    "relevance_score": 75,
                    "dependency_reasons": [],
                    "related_hostnames": [],
                    "recommended_for_direct": True,
                },
            ],
        },
        Mock(),
    )

    executor = Mock()
    executor.run.return_value = Mock(
        returncode=0,
        stdout="Name: MAXVPN_DIRECT\nMembers:\n",
        stderr="",
    )

    repository = Mock()
    repository.get_by_user.return_value = [
        Mock(
            enabled=True,
            action=Mock(value="direct"),
            target_type=Mock(value="domain"),
            target="maps.2gis.com",
        ),
    ]

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_runtime_executor] = lambda: executor
    app.dependency_overrides[get_repository] = lambda: repository

    try:
        response = client.get(
            "/api/v1/smart-routing/dependency-diagnostic/abc123",
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

    body = response.json()

    assert body["site_domain"] == "2gis.ru"
    assert body["summary"]["observed"] == 2
    assert body["summary"]["vpn"] == 1
    assert body["resources"][1]["candidate_for_direct"] is True


def test_commit_dependency_diagnostic_rules_accepts_observed_brand_alias_candidates():
    current_user = make_user()

    def candidate(hostname: str, ip: str):
        resource = Mock()
        resource.hostname = hostname
        resource.ips = (ip,)
        resource.candidate_for_direct = True
        resource.selection_allowed = True
        resource.synthetic = False
        return resource

    jam_resource = candidate("jam.api.2gis.com", "91.236.49.1")
    photo_resource = candidate("photo.2gis.com", "91.240.170.190")

    group = Mock()
    group.site_domain = "2gis.ru"
    group.resources = (jam_resource, photo_resource)

    service = Mock()
    service.get_group.return_value = group

    repository = Mock()
    repository.get_by_user.return_value = []

    executor = Mock()
    executor.run.return_value = Mock(
        returncode=0,
        stdout="Name: MAXVPN_DIRECT\nMembers:\n",
        stderr="",
    )

    dependency_group = Mock()
    dependency_group.id = 10
    dependency_group.items = []

    group_repository = Mock()
    group_repository.get_or_create.return_value = dependency_group

    db = Mock()
    next_rule_id = 100

    def flush():
        nonlocal next_rule_id
        rule = db.add.call_args.args[0]
        rule.id = next_rule_id
        next_rule_id += 1

    db.flush.side_effect = flush

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_group_repository] = lambda: group_repository
    app.dependency_overrides[get_runtime_executor] = lambda: executor
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post(
            "/api/v1/smart-routing/dependency-diagnostic/abc123/rules",
            json={
                "hostnames": ["jam.api.2gis.com", "photo.2gis.com"],
                "title": "2GIS",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["site_domain"] == "2gis.ru"
    assert body["group_id"] == 10
    assert body["apply_required"] is True
    assert len(body["created_rules"]) == 2
    assert body["reused_rules"] == []
    assert {rule["target"] for rule in body["created_rules"]} == {
        "jam.api.2gis.com",
        "photo.2gis.com",
    }
    assert {rule["id"] for rule in body["created_rules"]} == {100, 101}
    assert group_repository.get_or_create.called
    assert group_repository.add_rule.call_count == 2
    assert db.commit.called


def test_commit_rechecks_current_direct_ipset_and_rejects_stale_candidate():
    current_user = make_user()
    resource = Mock()
    resource.hostname = "jam.api.2gis.com"
    resource.ips = ("91.236.49.1",)
    resource.candidate_for_direct = True
    resource.selection_allowed = True
    resource.synthetic = False

    group = Mock()
    group.site_domain = "2gis.ru"
    group.resources = (resource,)

    service = Mock()
    service.get_group.return_value = group
    repository = Mock()
    repository.get_by_user.return_value = []
    executor = Mock()
    executor.run.return_value = Mock(
        returncode=0,
        stdout="Name: MAXVPN_DIRECT\nMembers:\n91.236.49.1\n",
        stderr="",
    )
    group_repository = Mock()
    db = Mock()

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_group_repository] = lambda: group_repository
    app.dependency_overrides[get_runtime_executor] = lambda: executor
    app.dependency_overrides[get_db] = lambda: db

    try:
        response = client.post(
            "/api/v1/smart-routing/dependency-diagnostic/abc123/rules",
            json={"hostnames": ["jam.api.2gis.com"], "title": "2GIS"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "no longer eligible" in response.json()["detail"]
    assert not db.commit.called


def test_commit_fails_closed_when_current_direct_ipset_cannot_be_read():
    current_user = make_user()
    resource = Mock()
    resource.hostname = "jam.api.2gis.com"
    resource.ips = ("91.236.49.1",)
    resource.candidate_for_direct = True
    resource.selection_allowed = True
    resource.synthetic = False
    group = Mock(site_domain="2gis.ru", resources=(resource,))
    service = Mock()
    service.get_group.return_value = group
    repository = Mock()
    repository.get_by_user.return_value = []
    executor = Mock()
    executor.run.return_value = Mock(
        returncode=1, stdout="", stderr="ipset unavailable"
    )
    db = Mock()

    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_runtime_executor] = lambda: executor
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_group_repository] = lambda: Mock()
    try:
        response = client.post(
            "/api/v1/smart-routing/dependency-diagnostic/abc123/rules",
            json={"hostnames": ["jam.api.2gis.com"]},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert not db.commit.called


def test_commit_rejects_synthetic_inferred_hostname():
    current_user = make_user()
    resource = Mock()
    resource.hostname = "maps.2gis.com"
    resource.ips = ("91.236.49.2",)
    resource.candidate_for_direct = False
    resource.selection_allowed = False
    resource.synthetic = True
    group = Mock(site_domain="2gis.ru", resources=(resource,))
    service = Mock()
    service.get_group.return_value = group
    repository = Mock()
    repository.get_by_user.return_value = []
    executor = Mock()
    executor.run.return_value = Mock(returncode=0, stdout="Members:\n", stderr="")
    db = Mock()
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_session_service] = lambda: service
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_runtime_executor] = lambda: executor
    app.dependency_overrides[get_group_repository] = lambda: Mock()
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.post(
            "/api/v1/smart-routing/dependency-diagnostic/abc123/rules",
            json={"hostnames": ["maps.2gis.com"]},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 400
    assert not db.commit.called
