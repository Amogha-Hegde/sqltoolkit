"""SQLite dialect helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import URL

from sqltoolkit.dialects._shared import ensure_empty, pop_bool, stringify_query


def build_sqlite_url(
    *,
    async_mode: bool,
    config: dict[str, Any],
    query: dict[str, Any],
) -> str:
    driver = config.pop("driver", "aiosqlite" if async_mode else "pysqlite")
    file_path = config.pop("file_path", None)
    database = config.pop("database", None)
    in_memory = pop_bool(config, "in_memory", False)

    if file_path and database:
        raise ValueError("SQLite config must use either file_path or database, not both")

    if in_memory:
        if file_path or database:
            raise ValueError("SQLite config cannot combine in_memory with file_path/database")
        database_name = ":memory:"
    else:
        database_name = file_path or database

    if not database_name:
        raise ValueError("SQLite config requires file_path, database, or in_memory=True")

    ensure_empty(config, "sqlite")

    return URL.create(
        drivername=f"sqlite+{driver}",
        database=str(database_name),
        query=stringify_query(query),
    ).render_as_string(hide_password=False)
