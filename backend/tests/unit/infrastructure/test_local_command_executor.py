import subprocess
from unittest.mock import Mock, patch

import pytest

from app.infrastructure.local_command_executor import (
    LocalCommandExecutor,
)


@patch("app.infrastructure.local_command_executor.subprocess.run")
def test_run_executes_command(
    subprocess_run: Mock,
) -> None:
    executor = LocalCommandExecutor()

    executor.run(
        [
            "wg",
            "show",
        ]
    )

    subprocess_run.assert_called_once_with(
        [
            "wg",
            "show",
        ],
        check=True,
    )


@patch("app.infrastructure.local_command_executor.subprocess.run")
def test_run_propagates_called_process_error(
    subprocess_run: Mock,
) -> None:
    subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["wg", "show"],
    )

    executor = LocalCommandExecutor()

    with pytest.raises(subprocess.CalledProcessError):
        executor.run(
            [
                "wg",
                "show",
            ]
        )
