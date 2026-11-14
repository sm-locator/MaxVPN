from __future__ import annotations

import time
from unittest.mock import Mock

import pytest
from backend.services.smart_routing_dependency_diagnostic import (
    SmartRoutingDependencyDnsParser,
)
from backend.services.smart_routing_dependency_diagnostic_session import (
    DependencyDiagnosticSession,
    SmartRoutingDependencyDiagnosticSessionService,
)


def test_get_group_rejects_session_while_observation_is_running():
    service = SmartRoutingDependencyDiagnosticSessionService(
        reader=Mock(), analyzer=Mock()
    )
    token = "active-session"
    session = DependencyDiagnosticSession(
        token=token,
        site_domain="2gis.ru",
        client_ip="192.168.8.231",
        started_at=time.time(),
        expires_at=time.time() + 60,
        cursor=Mock(),
        parser=SmartRoutingDependencyDnsParser(),
        last_group=Mock(),
    )
    service._sessions[token] = session

    with pytest.raises(ValueError, match="still running"):
        service.get_group(token)


def test_get_group_returns_result_after_observation_finishes():
    service = SmartRoutingDependencyDiagnosticSessionService(
        reader=Mock(), analyzer=Mock()
    )
    token = "finished-session"
    expected_group = Mock()
    now = time.time()
    session = DependencyDiagnosticSession(
        token=token,
        site_domain="2gis.ru",
        client_ip="192.168.8.231",
        started_at=now - 30,
        expires_at=now - 1,
        cursor=Mock(),
        parser=SmartRoutingDependencyDnsParser(),
        last_group=expected_group,
        last_poll_completed_at=now,
    )
    service._sessions[token] = session

    assert service.get_group(token) is expected_group


def test_get_group_requires_a_final_poll_after_expiration():
    service = SmartRoutingDependencyDiagnosticSessionService(
        reader=Mock(), analyzer=Mock()
    )
    token = "expired-without-final-poll"
    now = time.time()
    session = DependencyDiagnosticSession(
        token=token,
        site_domain="2gis.ru",
        client_ip="192.168.8.231",
        started_at=now - 60,
        expires_at=now - 10,
        cursor=Mock(),
        parser=SmartRoutingDependencyDnsParser(),
        last_group=Mock(),
        last_poll_completed_at=now - 11,
    )
    service._sessions[token] = session

    with pytest.raises(ValueError, match="final diagnostic results were not collected"):
        service.get_group(token)
