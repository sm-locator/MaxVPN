from backend.infrastructure.database.factory import create_server_repository
from backend.infrastructure.database.init_db import init_database


def main() -> None:
    print("Initializing database...")

    init_database()

    repository = create_server_repository()

    servers = repository.get_all()

    print("Database initialized successfully.")
    print(f"Loaded {len(servers)} servers:")

    for server in servers:
        print(
            f"  [{server.id}] "
            f"{server.country}/{server.city} "
            f"{server.name} "
            f"({server.endpoint})"
        )


if __name__ == "__main__":
    main()
