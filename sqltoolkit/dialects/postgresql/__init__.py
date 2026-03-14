"""PostgreSQL dialect helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import URL

from sqltoolkit.dialects._shared import ensure_empty, pop_int, stringify_query


def build_postgresql_url(
    *,
    async_mode: bool,
    config: dict[str, Any],
    query: dict[str, Any],
) -> str:
    driver = config.pop("driver", "asyncpg" if async_mode else "psycopg")
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
