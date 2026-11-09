from backend.infrastructure.config.settings import Settings


def test_default_amneziawg_settings() -> None:
    settings = Settings()

    assert settings.amneziawg_binary == "awg"
    assert settings.amneziawg_interface == "WireGuard"


def test_default_ssh_settings(monkeypatch) -> None:
    monkeypatch.delenv("SSH_PRIVATE_KEY_PATH", raising=False)

    settings = Settings()

    assert settings.ssh_host == "192.168.8.1"
    assert settings.ssh_port == 22
    assert settings.ssh_username == "root"
    assert settings.ssh_private_key_path == "~/.ssh/maxvpn_brume3"
