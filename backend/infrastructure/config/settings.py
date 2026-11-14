from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "MaxVPN"

    database_url: str = "sqlite:///maxvpn.db"

    export_directory: str = "./exports"

    wireguard_binary: str = "wg"

    wireguard_interface: str = "wg0"

    amneziawg_binary: str = "awg"

    amneziawg_interface: str = "WireGuard"

    ssh_host: str = "192.168.8.1"

    ssh_port: int = 22

    ssh_username: str = "root"

    ssh_private_key_path: str = "~/.ssh/maxvpn_brume3"

    wireguard_server_address: str = "10.100.0.1/24"

    wireguard_listen_port: int = 51820

    log_level: str = "INFO"

    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None

    secret_key: str | None = None
    vpn_config_encryption_key: str | None = None

    wireguard_server_public_key: str | None = None
    wireguard_endpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
