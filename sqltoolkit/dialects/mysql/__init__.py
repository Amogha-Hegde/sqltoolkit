"""MySQL dialect helpers."""

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


def build_mysql_url(
    *,
    async_mode: bool,
    config: dict[str, Any],
    query: dict[str, Any],
) -> str:
    driver = config.pop("driver", None) or ("aiomysql" if async_mode else "pymysql")
    charset = config.pop("charset", None)
    if charset is not None:
        query.setdefault("charset", charset)

    username = config.pop("username", config.pop("user", None))
    password = config.pop("password", None)
    host = config.pop("host", None)
    port = pop_int(config, "port")
    database = config.pop("database", config.pop("dbname", None))
    ensure_empty(config, "mysql")

    return URL.create(
        drivername=f"mysql+{driver}",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=stringify_query(query),
    ).render_as_string(hide_password=False)


def build_mysql_session_statements(settings: dict[str, Any]) -> list[str]:
    assignments: list[str] = []
    for name, value in settings.items():
        setting_name = validate_setting_name(str(name), dialect="mysql")
        rendered = stringify_setting_value(value, bool_mode="one_zero")
        if isinstance(value, str):
            rendered = sql_quote_string(rendered)
        assignments.append(f"SESSION {setting_name} = {rendered}")
    if not assignments:
        return []
    return ["SET " + ", ".join(assignments)]
