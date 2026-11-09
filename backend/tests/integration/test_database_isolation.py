from unittest.mock import Mock

import pytest
from backend.tests.integration.conftest import _test_database_url, truncate_all_tables
from sqlalchemy.orm import Session


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://database/maxvpn_test")

    with pytest.raises(pytest.UsageError, match="Set TEST_DATABASE_URL"):
        _test_database_url()


@pytest.mark.parametrize(
    "url",
    [
        "invalid-url",
        "sqlite:///maxvpn_test",
        "postgresql+psycopg://database/maxvpn",
        "postgresql+psycopg://database/maxvpn_test?dbname=maxvpn",
    ],
)
def test_database_url_rejects_unsafe_targets(monkeypatch, url):
    monkeypatch.setenv("TEST_DATABASE_URL", url)

    with pytest.raises(pytest.UsageError, match="TEST_DATABASE_URL"):
        _test_database_url()


def test_truncate_checks_the_actual_connected_database():
    session = Mock(spec=Session)
    session.execute.return_value.scalar_one.return_value = "maxvpn"

    with pytest.raises(RuntimeError, match="Refusing to truncate"):
        truncate_all_tables(session)

    session.execute.assert_called_once()
    assert str(session.execute.call_args.args[0]) == "SELECT current_database()"
    session.commit.assert_not_called()
