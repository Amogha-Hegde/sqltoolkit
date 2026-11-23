"""Core Oracle SQL function helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func


def oracle_sysdate() -> Any:
    """Return Oracle SYSDATE SQL expression."""
    return func.sysdate()


def oracle_systimestamp() -> Any:
    """Return Oracle SYSTIMESTAMP SQL expression."""
    return func.systimestamp()


def oracle_json_value(*args: Any) -> Any:
    """Return Oracle JSON_VALUE SQL expression."""
    return func.json_value(*args)


def oracle_nvl(*args: Any) -> Any:
    """Return Oracle NVL SQL expression."""
    return func.nvl(*args)


def oracle_to_char(*args: Any) -> Any:
    """Return Oracle TO_CHAR SQL expression."""
    return func.to_char(*args)


def oracle_json_query(*args: Any) -> Any:
    """Return Oracle JSON_QUERY SQL expression."""
    return func.json_query(*args)


def oracle_json_object(*args: Any, **kwargs: Any) -> Any:
    """Return Oracle JSON_OBJECT SQL expression."""
    return func.json_object(*args, **kwargs)
