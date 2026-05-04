"""Oracle dialect helpers and Oracle-specific extensions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import URL

from sqltoolkit.dialects._shared import (
    as_mapping,
    ensure_empty,
    pop_int,
    sql_quote_string,
    stringify_query,
    stringify_setting_value,
    validate_setting_name,
)
from sqltoolkit.dialects.oracle.custom_fields import (
    OracleBoolean,
    OracleJSON,
    OracleTimezoneAwareDateTime,
)
from sqltoolkit.dialects.oracle.functions import (
    oracle_json_object,
    oracle_json_query,
    oracle_json_value,
    oracle_nvl,
    oracle_paginate,
    oracle_sysdate,
    oracle_systimestamp,
    oracle_to_char,
)
from sqltoolkit.dialects.registry import register_custom_type, register_function


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


def build_oracle_session_statements(settings: dict[str, Any]) -> list[str]:
    statements: list[str] = []
    for name, value in settings.items():
        setting_name = validate_setting_name(str(name), dialect="oracle")
        rendered = stringify_setting_value(value)
        if isinstance(value, str):
            rendered = sql_quote_string(rendered)
        statements.append(f"ALTER SESSION SET {setting_name} = {rendered}")
    return statements


register_custom_type("oracle", "json", OracleJSON)
register_custom_type("oracle", "timezone_aware_datetime", OracleTimezoneAwareDateTime)
register_custom_type("oracle", "datetime_tz", OracleTimezoneAwareDateTime)
register_custom_type("oracle", "boolean", OracleBoolean)
register_custom_type("oracle", "bool", OracleBoolean)

register_function("oracle", "sysdate", oracle_sysdate)
register_function("oracle", "systimestamp", oracle_systimestamp)
register_function("oracle", "json_value", oracle_json_value)
register_function("oracle", "nvl", oracle_nvl)
register_function("oracle", "to_char", oracle_to_char)
register_function("oracle", "json_query", oracle_json_query)
register_function("oracle", "json_object", oracle_json_object)
register_function("oracle", "paginate", oracle_paginate)
