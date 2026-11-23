"""Oracle boolean custom field."""

from __future__ import annotations

from typing import Any

from sqlalchemy.types import SmallInteger, TypeDecorator


class OracleBoolean(TypeDecorator):
    """Oracle-compatible boolean storage backed by a small integer column."""

    impl = SmallInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> int | None:
        """Convert Python bool values to Oracle-compatible integers."""
        if value is None:
            return None
        if not isinstance(value, bool):
            raise ValueError(f"OracleBoolean only accepts bool, got: {type(value).__name__}")
        return 1 if value else 0

    def process_result_value(self, value: Any, dialect: Any) -> bool | None:
        """Convert Oracle integer values back to Python bools."""
        if value is None:
            return None
        if value not in (0, 1):
            raise ValueError(f"Invalid boolean in DB: {value}")
        return bool(value)

    @property
    def python_type(self) -> type[bool]:
        """Return the Python type represented by this decorator."""
        return bool
