import argparse

from backend.application.container import build_create_client_use_case
from backend.application.context.default_context import (
    create_default_context,
)
from backend.infrastructure.database.init_db import init_database
from backend.services.wireguard_config_renderer import WireGuardConfigRenderer


def main(args: argparse.Namespace | None = None) -> None:
    print("Initializing database...")

    init_database()

    print("Creating client configuration...")

    use_case = build_create_client_use_case()

    config = use_case.execute(
        create_default_context(),
    )

    if config is None:
        print("No suitable server found.")
        return

    renderer = WireGuardConfigRenderer()

    text = renderer.render(config)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(text)

        print(f"Configuration written to: {args.output}")
    else:
        print()
        print("=" * 60)
        print(text)
        print("=" * 60)


if __name__ == "__main__":
    main()
