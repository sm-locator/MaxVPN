from app.vpn.executors.local import LocalCommandExecutor


def test_echo() -> None:
    executor = LocalCommandExecutor()

    result = executor.run(["echo", "Hello"])

    assert result.stdout == "Hello"
    assert result.stderr == ""
    assert result.returncode == 0
