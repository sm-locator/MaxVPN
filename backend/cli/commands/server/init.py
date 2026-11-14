from __future__ import annotations

import argparse

from backend.application.container import (
    build_initialize_wireguard_server_use_case,
)
from backend.infrastructure.config.settings import get_settings


def main(args: argparse.Namespace | None = None) -> None:
    if args is None:
        raise RuntimeError("CLI arguments are required.")

    settings = get_settings()

    print("Initializing WireGuard server...")

    use_case = build_initialize_wireguard_server_use_case()
    server = use_case.execute(server_id=args.server_id)

    print("WireGuard server initialized successfully.")
    print(f"Server:      {server.name}")
    print(f"Interface:   {settings.wireguard_interface}")
    print(f"Address:     {settings.wireguard_server_address}")
    print(f"Listen port: {settings.wireguard_listen_port}")
    print(f"Public key:  {server.public_key}")
