"""Dialect helpers for sqltoolkit."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._shared import as_mapping, merge_db_url_query, normalize_db_url
from .mssql import build_mssql_url
from .mssql import build_mssql_session_statements
from .mysql import build_mysql_url
from .mysql import build_mysql_session_statements
from .oracle import build_oracle_connect_args, build_oracle_url
from .oracle import build_oracle_session_statements
from .postgresql import build_postgresql_session_statements
from .postgresql import build_postgresql_url
from .registry import (
    DialectFunctionNamespace,
    build_custom_type,
    call_dialect_function,
    get_custom_type_factory,
    get_function_factory,
    list_custom_types,
    list_functions,
)
from .sqlite import build_sqlite_url
from .sqlite import build_sqlite_session_statements

SUPPORTED_DIALECTS = frozenset({"postgresql", "oracle", "mysql", "mssql", "sqlite"})


def normalize_dialect(dialect: str) -> str:
    """Normalize and validate a supported dialect name."""
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
    """Build a SQLAlchemy database URL from raw dialect config."""
    dialect_name = normalize_dialect(dialect)
    data = dict(config)
    db_url = data.pop("db_url", None) or data.pop("url", None)
    query = as_mapping(data.pop("query", {}))
    database_options = as_mapping(data.pop("database_options", {}))
    if database_options:
        query = {**database_options, **query}
    if db_url:
        normalized_url = normalize_db_url(str(db_url))
        if query:
            return merge_db_url_query(normalized_url, query)
        return normalized_url

    builder = {
        "postgresql": build_postgresql_url,
        "mysql": build_mysql_url,
        "oracle": build_oracle_url,
        "mssql": build_mssql_url,
        "sqlite": build_sqlite_url,
    }[dialect_name]
    return builder(async_mode=async_mode, config=data, query=query)


def build_session_statements(
    *,
    dialect: str,
    settings: Mapping[str, Any],
) -> list[str]:
    """Build backend-specific session setup statements."""
    dialect_name = normalize_dialect(dialect)
    mapping = as_mapping(settings)
    if not mapping:
        return []

    builder = {
        "postgresql": build_postgresql_session_statements,
        "mysql": build_mysql_session_statements,
        "oracle": build_oracle_session_statements,
        "mssql": build_mssql_session_statements,
        "sqlite": build_sqlite_session_statements,
    }[dialect_name]
    return builder(mapping)


def get_custom_type(dialect: str, name: str, *args: Any, **kwargs: Any) -> Any:
    """Instantiate a dialect-specific custom SQLAlchemy type."""

    return build_custom_type(dialect, name, *args, **kwargs)


def get_custom_type_class(dialect: str, name: str) -> Any:
    """Return the registered type factory or class for a dialect-specific custom type."""

    return get_custom_type_factory(dialect, name)


def get_dialect_function(dialect: str, name: str, *args: Any, **kwargs: Any) -> Any:
    """Build a SQL expression for a dialect-specific function."""

    return call_dialect_function(dialect, name, *args, **kwargs)


def get_dialect_function_factory(dialect: str, name: str) -> Any:
    """Return the registered callable or function class for a dialect-specific function."""

    return get_function_factory(dialect, name)


def get_dialect_functions(dialect: str) -> DialectFunctionNamespace:
    """Return an attribute-based namespace for dialect-specific SQL functions."""

    return DialectFunctionNamespace(dialect)
