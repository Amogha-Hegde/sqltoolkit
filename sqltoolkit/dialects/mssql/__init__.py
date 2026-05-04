"""MSSQL dialect helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.engine import URL

from sqltoolkit.dialects._shared import (
    ensure_empty,
    pop_int,
    stringify_query,
    stringify_setting_value,
    validate_setting_name,
)


def build_mssql_url(
    *,
    async_mode: bool,
    config: dict[str, Any],
    query: dict[str, Any],
) -> str:
    driver = config.pop("driver", "aioodbc" if async_mode else "pyodbc")
    username = config.pop("username", config.pop("user", None))
    password = config.pop("password", None)
    host = config.pop("host", None)
    port = pop_int(config, "port")
    database = config.pop("database", config.pop("dbname", None))
    dsn_name = config.pop("dsn_name", config.pop("dsn", None))
    odbc_connect = config.pop("odbc_connect", None)
    odbc_driver = config.pop("odbc_driver", None)

    if odbc_driver is not None:
        query.setdefault("driver", odbc_driver)

    if odbc_connect is not None and any((host, port, database, dsn_name)):
        raise ValueError("MSSQL config cannot combine odbc_connect with host/port/database/dsn_name")

    ensure_empty(config, "mssql")

    drivername = f"mssql+{driver}"
    if odbc_connect is not None:
        query.setdefault("odbc_connect", odbc_connect)
        return URL.create(
            drivername=drivername,
            query=stringify_query(query),
        ).render_as_string(hide_password=False)

    if dsn_name is not None:
        return URL.create(
            drivername=drivername,
            username=username,
            password=password,
            host=dsn_name,
            query=stringify_query(query),
        ).render_as_string(hide_password=False)

    return URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
        query=stringify_query(query),
    ).render_as_string(hide_password=False)


def build_mssql_session_statements(settings: dict[str, Any]) -> list[str]:
    statements: list[str] = []
    for name, value in settings.items():
        setting_name = validate_setting_name(str(name), dialect="mssql")
        rendered = stringify_setting_value(value, bool_mode="on_off").upper()
        if isinstance(value, str):
            rendered = str(value)
        statements.append(f"SET {setting_name} {rendered}")
    return statements
