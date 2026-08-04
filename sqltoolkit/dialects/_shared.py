"""Shared helpers for dialect-specific builders."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from sqlalchemy.engine import URL, make_url

_SIMPLE_SETTING_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$.]*$")
_MSSQL_SETTING_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]*$")


def as_mapping(value: Any) -> dict[str, Any]:
    """Return a copy of a mapping value, treating empty values as absent."""
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Expected a mapping value")
    return dict(value)


def stringify_query(query: Mapping[str, Any]) -> dict[str, str]:
    """Convert URL query parameters to strings for SQLAlchemy URLs."""
    return {str(key): str(value) for key, value in query.items()}


def pop_int(config: dict[str, Any], key: str) -> int | None:
    """Pop an optional integer value from a config mapping."""
    value = config.pop(key, None)
    if value in (None, ""):
        return None
    return int(value)


def pop_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    """Pop an optional boolean value from a config mapping."""
    value = config.pop(key, None)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def ensure_empty(config: dict[str, Any], dialect: str) -> None:
    """Raise if a dialect builder did not consume every config field."""
    leftovers = sorted(config)
    if leftovers:
        raise ValueError(f"Unsupported {dialect} config fields: {', '.join(leftovers)}")


def normalize_db_url(db_url: str) -> str:
    """Normalize a DB URL so credential components are rendered safely.

    This protects passwords when the URL is otherwise valid. If callers provide
    a malformed URL where reserved characters in the password were never escaped,
    SQLAlchemy may parse it ambiguously; in that case callers should use
    structured fields like username/password instead of a raw db_url.
    """

    parsed = make_url(db_url)
    if isinstance(parsed, URL):
        return parsed.render_as_string(hide_password=False)
    return str(parsed)


def merge_db_url_query(db_url: str, query: Mapping[str, Any]) -> str:
    """Merge extra query parameters into a DB URL.

    Explicit values supplied in ``query`` override the same keys already
    present in ``db_url``.
    """

    parsed = make_url(db_url)
    merged_query = {**parsed.query, **stringify_query(query)}
    if isinstance(parsed, URL):
        return parsed.set(query=merged_query).render_as_string(hide_password=False)
    return str(parsed)


def validate_setting_name(name: str, *, dialect: str) -> str:
    """Validate a backend session setting name."""
    stripped = name.strip()
    if not stripped:
        raise ValueError("Session setting names must not be empty")

    pattern = _MSSQL_SETTING_NAME if dialect == "mssql" else _SIMPLE_SETTING_NAME
    if not pattern.match(stripped):
        raise ValueError(f"Unsupported {dialect} session setting name: {name!r}")
    return stripped


def sql_quote_string(value: str) -> str:
    """Return a single-quoted SQL string literal."""
    return "'" + value.replace("'", "''") + "'"


def stringify_setting_value(value: Any, *, bool_mode: str = "true_false") -> str:
    """Render a Python setting value as backend session SQL text."""
    if isinstance(value, bool):
        if bool_mode == "on_off":
            return "on" if value else "off"
        if bool_mode == "one_zero":
            return "1" if value else "0"
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(stringify_setting_value(item, bool_mode=bool_mode) for item in value)
    return str(value)
