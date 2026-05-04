"""Core Oracle SQL function helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func


def oracle_sysdate() -> Any:
    return func.sysdate()


def oracle_systimestamp() -> Any:
    return func.systimestamp()


def oracle_json_value(*args: Any) -> Any:
    return func.json_value(*args)


def oracle_nvl(*args: Any) -> Any:
    return func.nvl(*args)


def oracle_to_char(*args: Any) -> Any:
    return func.to_char(*args)


def oracle_json_query(*args: Any) -> Any:
    return func.json_query(*args)


def oracle_json_object(*args: Any, **kwargs: Any) -> Any:
    return func.json_object(*args, **kwargs)
