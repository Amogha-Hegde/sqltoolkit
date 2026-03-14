"""Oracle dialect helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import URL

from sqltoolkit.dialects._shared import as_mapping, ensure_empty, pop_int, stringify_query


def build_oracle_url(
    *,
    async_mode: bool,
    config: dict[str, Any],
    query: dict[str, Any],
) -> str:
    driver = config.pop("driver", "oracledb")
    username = config.pop("username", config.pop("user", None))
    password = config.pop("password", None)
    host = config.pop("host", None)
    port = pop_int(config, "port")
    service_name = config.pop("service_name", None)
    sid = config.pop("sid", None)
    database = config.pop("database", None)
    dsn = config.pop("dsn", None)

    if dsn and any((host, port, service_name, sid, database)):
        raise ValueError("Oracle config cannot combine dsn with host/port/service_name/sid/database")
    if service_name and (sid or database):
        raise ValueError("Oracle config must use either service_name or sid/database, not both")

    ensure_empty(config, "oracle")

    drivername = f"oracle+{driver}"
    if dsn:
        return URL.create(drivername=drivername).render_as_string(hide_password=False)

    if service_name:
        query.setdefault("service_name", service_name)
        database_name = None
    else:
        database_name = sid or database

    return URL.create(
        drivername=drivername,
        username=username,
        password=password,
        host=host,
        port=port,
        database=database_name,
        query=stringify_query(query),
    ).render_as_string(hide_password=False)


def build_oracle_connect_args(config: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(config)
    connect_args = as_mapping(data.pop("connect_args", {}))
    dsn = data.get("dsn")
    username = data.get("username", data.get("user"))
    password = data.get("password")

    if dsn:
        connect_args.setdefault("dsn", dsn)
        if username is not None:
            connect_args.setdefault("user", username)
        if password is not None:
            connect_args.setdefault("password", password)

    return connect_args
