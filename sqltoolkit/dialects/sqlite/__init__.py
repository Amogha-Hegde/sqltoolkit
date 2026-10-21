"""SQLite dialect helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import URL

from sqltoolkit.dialects._shared import (
    ensure_empty,
    pop_bool,
    render_url,
    sql_quote_string,
    stringify_query,
    stringify_setting_value,
    validate_setting_name,
)


def build_sqlite_url(
    *,
    async_mode: bool,
    config: dict[str, Any],
    query: dict[str, Any],
) -> str:
    """Build a SQLite SQLAlchemy URL from structured config."""
    driver = config.pop("driver", None) or ("aiosqlite" if async_mode else "pysqlite")
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

    return render_url(URL.create(
        drivername=f"sqlite+{driver}",
        database=str(database_name),
        query=stringify_query(query),
    ))


def build_sqlite_session_statements(settings: dict[str, Any]) -> list[str]:
    """Build SQLite PRAGMA setup statements."""
    statements: list[str] = []
    for name, value in settings.items():
        pragma_name = validate_setting_name(str(name), dialect="sqlite")
        rendered = stringify_setting_value(value, bool_mode="one_zero")
        if isinstance(value, str):
            rendered = sql_quote_string(rendered)
        statements.append(f"PRAGMA {pragma_name} = {rendered}")
    return statements
