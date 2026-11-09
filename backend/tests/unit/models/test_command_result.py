from backend.models.command_result import CommandResult


def test_command_result_stores_command_output() -> None:
    result = CommandResult(
        stdout="ok",
        stderr="",
        returncode=0,
    )

    assert result.stdout == "ok"
    assert result.stderr == ""
    assert result.returncode == 0
