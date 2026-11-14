from unittest.mock import patch

from backend.infrastructure.database.dry_run_unit_of_work import (
    DryRunUnitOfWork,
)
from backend.infrastructure.database.session import SessionFactory


def test_dry_run_unit_of_work_does_not_commit():
    session = SessionFactory()

    try:
        unit_of_work = DryRunUnitOfWork(session)

        with patch.object(session, "commit") as commit:
            unit_of_work.commit()

        commit.assert_not_called()
    finally:
        session.rollback()
        session.close()
