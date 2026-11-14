from __future__ import annotations

import argparse
from pathlib import Path

from backend.application.container import (
    build_export_existing_client_config_use_case,
)
from backend.infrastructure.config.settings import get_settings
from backend.infrastructure.database.init_db import init_database


def main(args: argparse.Namespace) -> None:
    print("Initializing database...")
    init_database()

    settings = get_settings()

    if args.output:
        destination = Path(args.output)
    else:
        destination = Path(settings.export_directory) / f"{args.name}.conf"

    use_case = build_export_existing_client_config_use_case()

    destination = use_case.execute(
        client_name=args.name,
        destination=destination,
    )

    print("Client configuration exported successfully.")
    print(f"Name:   {args.name}")
    print(f"Config: {destination}")
