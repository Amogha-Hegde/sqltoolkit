"""PostgreSQL dialect helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import URL

from sqltoolkit.dialects._shared import (
    ensure_empty,
    pop_int,
    sql_quote_string,
    stringify_query,
    stringify_setting_value,
    validate_setting_name,
)


def build_postgresql_url(
    *,
    async_mode: bool,
    config: dict[str, Any],
    query: dict[str, Any],
) -> str:
    """Build a PostgreSQL SQLAlchemy URL from structured config."""
    driver = config.pop("driver", None) or ("asyncpg" if async_mode else "psycopg")
    username = config.pop("username", config.pop("user", None))
    password = config.pop("password", None)
    host = config.pop("host", None)
    port = pop_int(config, "port")
    database = config.pop("database", config.pop("dbname", None))
    ensure_empty(config, "postgresql")

    return URL.create(
        drivername=f"postgresql+{driver}",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=stringify_query(query),
    ).render_as_string(hide_password=False)


def build_postgresql_session_statements(settings: dict[str, Any]) -> list[str]:
    """Build PostgreSQL per-connection setup statements."""
    statements: list[str] = []
    for name, value in settings.items():
        setting_name = validate_setting_name(str(name), dialect="postgresql")
        setting_value = stringify_setting_value(value, bool_mode="on_off")
        statements.append(
            "SELECT pg_catalog.set_config("
            f"{sql_quote_string(setting_name)}, "
            f"{sql_quote_string(setting_value)}, "
            "false)"
        )
    return statements
