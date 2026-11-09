from __future__ import annotations

import argparse

from backend.cli.commands.client.create import main as create_client
from backend.cli.commands.client.export import main as export_client
from backend.cli.commands.generate import main as generate
from backend.cli.commands.init import main as init_database
from backend.cli.commands.server.init import main as init_wireguard_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maxvpn",
        description="MaxVPN command line interface.",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "init",
        help="Initialize database.",
    )

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate WireGuard client configuration.",
    )

    generate_parser.add_argument(
        "--output",
        type=str,
        help="Write configuration to a file.",
    )

    client_parser = subparsers.add_parser(
        "client",
        help="Manage VPN clients.",
    )

    client_subparsers = client_parser.add_subparsers(
        dest="client_command",
        required=True,
    )

    create_parser = client_subparsers.add_parser(
        "create",
        help="Create and register a VPN client.",
    )

    create_parser.add_argument(
        "--name",
        required=True,
        type=str,
        help="Client name.",
    )

    create_parser.add_argument(
        "--description",
        type=str,
        help="Client description.",
    )

    create_parser.add_argument(
        "--output",
        type=str,
        help="Write WireGuard configuration to a file.",
    )

    create_parser.add_argument(
        "--dry-run",
        action="store_true",
        help=("Simulate client creation without changing the database or WireGuard."),
    )

    export_parser = client_subparsers.add_parser(
        "export",
        help="Export configuration of an existing VPN client.",
    )

    export_parser.add_argument(
        "--name",
        required=True,
        type=str,
        help="Existing client name.",
    )

    export_parser.add_argument(
        "--output",
        type=str,
        help="Write WireGuard configuration to a file.",
    )

    server_parser = subparsers.add_parser(
        "server",
        help="Manage the WireGuard server.",
    )

    server_subparsers = server_parser.add_subparsers(
        dest="server_command",
        required=True,
    )

    server_init_parser = server_subparsers.add_parser(
        "init",
        help="Initialize the WireGuard server interface.",
    )

    server_init_parser.add_argument(
        "--server-id",
        required=True,
        type=int,
        help="ID of the VPN server to initialize.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        init_database()
        return

    if args.command == "generate":
        generate(args)
        return

    if args.command == "client" and args.client_command == "create":
        create_client(args)
        return

    if args.command == "server" and args.server_command == "init":
        init_wireguard_server(args)
        return

    if args.command == "client" and args.client_command == "export":
        export_client(args)
        return


if __name__ == "__main__":
    main()
