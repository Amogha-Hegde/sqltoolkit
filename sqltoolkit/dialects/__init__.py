"""Dialect helpers for sqltoolkit."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._shared import as_mapping, normalize_db_url
from .mssql import build_mssql_url
from .mysql import build_mysql_url
from .oracle import build_oracle_connect_args, build_oracle_url
from .postgresql import build_postgresql_url
from .sqlite import build_sqlite_url

SUPPORTED_DIALECTS = frozenset({"postgresql", "oracle", "mysql", "mssql", "sqlite"})


def normalize_dialect(dialect: str) -> str:
    normalized = dialect.strip().lower()
    if normalized not in SUPPORTED_DIALECTS:
        supported = ", ".join(sorted(SUPPORTED_DIALECTS))
        raise ValueError(f"Unsupported dialect '{dialect}'. Supported dialects: {supported}")
    return normalized


def build_engine_url(
    *,
    dialect: str,
    async_mode: bool,
    config: Mapping[str, Any],
) -> str:
    dialect_name = normalize_dialect(dialect)
    data = dict(config)
    db_url = data.pop("db_url", None) or data.pop("url", None)
    if db_url:
        return normalize_db_url(str(db_url))

    query = as_mapping(data.pop("query", {}))
    builder = {
        "postgresql": build_postgresql_url,
        "mysql": build_mysql_url,
        "oracle": build_oracle_url,
        "mssql": build_mssql_url,
        "sqlite": build_sqlite_url,
    }[dialect_name]
    return builder(async_mode=async_mode, config=data, query=query)
