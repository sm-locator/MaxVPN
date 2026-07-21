from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    WIREGUARD_SERVER_PUBLIC_KEY: str = "server_public_key"
    WIREGUARD_ENDPOINT: str = "vpn.example.com:51820"

    WIREGUARD_DNS: str = "1.1.1.1"
    WIREGUARD_ALLOWED_IPS: str = "0.0.0.0/0"
    WIREGUARD_PERSISTENT_KEEPALIVE: int = 25

    model_config = SettingsConfigDict(
        env_file=".env",
    )


settings = Settings()
