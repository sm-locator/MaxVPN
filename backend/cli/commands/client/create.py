from __future__ import annotations

import argparse
from pathlib import Path

from backend.application.container import (
    build_create_client_use_case,
    build_register_client_use_case,
)
from backend.application.context.default_context import create_default_context
from backend.application.use_cases.export_client_config import (
    ExportClientConfigUseCase,
)
from backend.infrastructure.config.settings import get_settings
from backend.infrastructure.database.init_db import init_database
from backend.services.wireguard_config_renderer import WireGuardConfigRenderer


def main(args: argparse.Namespace) -> None:
    print("Initializing database...")
    init_database()

    print(f"Creating client: {args.name}")

    create_client = build_create_client_use_case()

    config = create_client.execute(
        create_default_context(),
    )

    if config is None:
        print("No suitable server found.")
        return

    register_client = build_register_client_use_case(
        dry_run=args.dry_run,
    )

    client = register_client.execute(
        config=config,
        name=args.name,
        description=args.description,
    )

    settings = get_settings()
    renderer = WireGuardConfigRenderer()
    exporter = ExportClientConfigUseCase(renderer)

    if args.output:
        destination = Path(args.output)
    else:
        destination = Path(settings.export_directory) / f"{client.name}.conf"

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    exporter.execute(
        config=config,
        destination=destination,
    )

    print()

    if args.dry_run:
        print("Dry run completed successfully.")
        print("No database changes were committed.")
        print("No WireGuard changes were made.")
    else:
        print("Client created successfully.")

    print(f"ID:          {client.id}")
    print(f"Name:        {client.name}")
    print(f"Server:      {config.server.name}")
    print(f"Address:     {client.address}")
    print(f"Public key:  {client.public_key}")
    print(f"Config:      {destination}")
