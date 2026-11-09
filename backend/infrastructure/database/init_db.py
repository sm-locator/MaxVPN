from backend.infrastructure.database.base import Base
from backend.infrastructure.database.models import ClientModel, ServerModel
from backend.infrastructure.database.seeds.seed import seed_database
from backend.infrastructure.database.session import SessionFactory, engine
from sqlalchemy import inspect


def init_database(engine_override=None, session_factory_override=None) -> None:
    engine_to_use = engine_override or engine
    session_factory = session_factory_override or SessionFactory

    # Keep ORM models imported before creating the schema so that
    # all mapped tables are registered in Base.metadata.
    _ = ClientModel, ServerModel

    with engine_to_use.begin() as connection:
        schema = inspect(connection)
        for table in Base.metadata.sorted_tables:
            if not schema.has_table(table.name):
                continue
            columns = {column["name"] for column in schema.get_columns(table.name)}
            missing = {column.name for column in table.columns} - columns
            if missing:
                raise RuntimeError(
                    f"Legacy CLI database schema does not match table {table.name}; "
                    f"missing columns {', '.join(sorted(missing))}"
                )
        Base.metadata.create_all(connection)

    session = session_factory()

    try:
        seed_database(session)
    finally:
        session.close()
