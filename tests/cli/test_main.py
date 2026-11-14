from backend.cli.main import build_parser


def test_client_create_command_is_available():
    parser = build_parser()

    args = parser.parse_args(
        [
            "client",
            "create",
            "--name",
            "phone",
        ]
    )

    assert args.command == "client"
    assert args.client_command == "create"
    assert args.name == "phone"
    assert args.description is None
    assert args.output is None


def test_client_create_accepts_description_and_output():
    parser = build_parser()

    args = parser.parse_args(
        [
            "client",
            "create",
            "--name",
            "phone",
            "--description",
            "My phone",
            "--output",
            "phone.conf",
        ]
    )

    assert args.command == "client"
    assert args.client_command == "create"
    assert args.name == "phone"
    assert args.description == "My phone"
    assert args.output == "phone.conf"


def test_server_init_command_is_available():
    parser = build_parser()

    args = parser.parse_args(
        [
            "server",
            "init",
            "--server-id",
            "1",
        ]
    )

    assert args.command == "server"
    assert args.server_command == "init"
    assert args.server_id == 1
