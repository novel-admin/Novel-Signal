import sqlite3

from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def register_sqlite_compatibility(
    dbapi_connection: object, _connection_record: object
) -> None:
    """Provide PostgreSQL functions used by shared metadata to SQLite tests."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function(
            "btrim", 1, lambda value: value.strip(), deterministic=True
        )
