"""Data-preservation checks, restricted to the disposable Compose database."""

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import MetaData, create_engine, select, text
from sqlalchemy.engine import make_url

from alembic import command
from alembic.config import Config

MAIN_REVISION = "c5c9faf426ba"
PROFILE_REVISION = "2a6f19c4b8d1"


def database():
    url = make_url(os.environ["ALEMBIC_DATABASE_URL"])
    if (
        os.environ.get("MAXVPN_DISPOSABLE_DATABASE") != "1"
        or url.host != "database"
        or url.database not in {"maxvpn_test", "maxvpn_restore_test"}
    ):
        raise RuntimeError("Refusing to modify a non-disposable database")
    return create_engine(url)


def migrate(revision):
    config = Config("backend/alembic.ini")
    config.set_main_option("script_location", "backend/alembic")
    command.upgrade(config, revision)


def snapshot(engine):
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.connect() as conn:
        tables = {}
        for name, table in metadata.tables.items():
            order = list(table.primary_key.columns) or list(table.columns)
            rows = conn.execute(select(table).order_by(*order)).mappings()
            tables[name] = [dict(row) for row in rows]
        sequence_rows = conn.execute(
            text(
                "SELECT sequencename, last_value FROM pg_sequences "
                "WHERE schemaname = 'public' ORDER BY sequencename"
            )
        ).all()
        sequences = [list(row) for row in sequence_rows]
    # Normalize timestamps, INET and other PostgreSQL values without logging data.
    return json.loads(
        json.dumps({"tables": tables, "sequences": sequences}, default=str)
    )


def verify(engine, before, upgraded):
    after = snapshot(engine)
    for name, rows in before["tables"].items():
        if upgraded and name == "alembic_version":
            continue
        current = after["tables"].get(name)
        if current is None or len(current) != len(rows):
            raise RuntimeError(f"Table or row count changed: {name}")
        for old, new in zip(rows, current, strict=True):
            if any(new.get(column) != value for column, value in old.items()):
                raise RuntimeError(f"Existing data changed: {name}")
    sequences = dict(after["sequences"])
    for name, value in before["sequences"]:
        if sequences.get(name) != value:
            raise RuntimeError(f"Sequence changed: {name}")
    if upgraded:
        from alembic.script import ScriptDirectory

        config = Config("backend/alembic.ini")
        config.set_main_option("script_location", "backend/alembic")
        head = ScriptDirectory.from_config(config).get_current_head()
        if after["tables"]["alembic_version"] != [{"version_num": head}]:
            raise RuntimeError("Database did not reach the migration head")
    print(f"Preserved {len(before['tables'])} tables, all rows/columns and sequences")


def reset(engine):
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def seed(engine, revision):
    if revision not in {MAIN_REVISION, PROFILE_REVISION}:
        raise ValueError("Unsupported fixture revision")
    reset(engine)
    migrate(revision)
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.begin() as conn:

        def insert(table, **values):
            return conn.execute(
                metadata.tables[table].insert().values(**values)
            ).inserted_primary_key[0]

        for index, role in enumerate(("admin", "user"), start=1):
            user = insert(
                "users",
                email=f"upgrade-{role}@example.test",
                password_hash=f"hash-{role}",
                role=role,
            )
            server = insert(
                "servers",
                name=f"server-{index}",
                country="Test",
                city="Lab",
                hostname=f"vpn-{index}.example.test",
                public_ip=f"192.0.2.{index}",
                wireguard_port=51820,
                status="active",
                enabled=index == 1,
            )
            insert(
                "clients",
                user_id=user,
                server_id=server,
                name=f"client-{index}",
                private_key=f"test-private-{index}",
                public_key=f"test-public-{index}",
                preshared_key=None if index == 1 else "test-psk",
                address=f"10.8.0.{index + 1}/32",
                dns="1.1.1.1",
                enabled=index == 1,
                allowed_ips="0.0.0.0/0",
                persistent_keepalive=25,
            )
            insert(
                "wireguard_clients",
                name=f"legacy-{index}",
                private_key=f"legacy-private-{index}",
                public_key=f"legacy-public-{index}",
                ip_address=f"10.9.0.{index + 1}",
            )
            if revision == PROFILE_REVISION:
                from cryptography.fernet import Fernet

                from backend.services.vpn_config_cipher import VPNConfigCipher

                cipher = VPNConfigCipher(Fernet.generate_key().decode())
                encrypted = cipher.encrypt("disposable test configuration")
                insert(
                    "vpn_profiles",
                    user_id=user,
                    name=f"AWG профиль {index}",
                    enabled=index == 1,
                    encrypted_provider_config=encrypted,
                )
                insert(
                    "vless_profiles",
                    user_id=user,
                    name=f"VLESS {index}",
                    enabled=index == 1,
                    encrypted_config=encrypted,
                )
                for target_type, target, family in (
                    ("domain", f"example{index}.test", "any"),
                    ("cidr", f"198.51.{index}.0/24", "ipv4"),
                    ("cidr", f"2001:db8:{index}::/48", "ipv6"),
                ):
                    rule = insert(
                        "smart_routing_rules",
                        user_id=user,
                        target_type=target_type,
                        target=target,
                        address_family=family,
                        action="direct",
                        priority=100 + index,
                        enabled=index == 1,
                    )
                    if target_type == "domain":
                        group = insert(
                            "smart_routing_dependency_groups",
                            user_id=user,
                            site_domain=target,
                            title="Test group",
                        )
                        insert(
                            "smart_routing_dependency_group_items",
                            group_id=group,
                            rule_id=rule,
                            source="diagnostic",
                        )
    print(f"Seeded representative data at {revision}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["reset", "seed", "snapshot", "verify", "upgrade-verify"]
    )
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    engine = database()
    if args.action == "reset":
        reset(engine)
    elif args.action == "seed":
        seed(engine, args.argument)
    elif args.action == "snapshot":
        path = Path(args.argument)
        baseline = snapshot(engine)
        with open(
            path, "w", opener=lambda name, flags: os.open(name, flags, 0o600)
        ) as output:
            json.dump(baseline, output)
        counts = ", ".join(
            f"{name}={len(rows)}" for name, rows in sorted(baseline["tables"].items())
        )
        print(f"Snapshot row counts: {counts}")
    else:
        before = json.loads(Path(args.argument).read_text())
        upgraded = args.action == "upgrade-verify"
        if upgraded:
            migrate("head")
        verify(engine, before, upgraded)
    engine.dispose()


if __name__ == "__main__":
    main()
