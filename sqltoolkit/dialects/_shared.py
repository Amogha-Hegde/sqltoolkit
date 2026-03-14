"""Shared helpers for dialect-specific builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import URL, make_url


def as_mapping(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("Expected a mapping value")
    return dict(value)


def stringify_query(query: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): str(value) for key, value in query.items()}


def pop_int(config: dict[str, Any], key: str) -> int | None:
    value = config.pop(key, None)
    if value in (None, ""):
        return None
    return int(value)


def pop_bool(config: dict[str, Any], key: str, default: bool) -> bool:
    value = config.pop(key, None)
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def ensure_empty(config: dict[str, Any], dialect: str) -> None:
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
