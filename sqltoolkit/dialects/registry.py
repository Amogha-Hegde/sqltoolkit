"""Registry for dialect-specific custom types and SQL functions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SUPPORTED_DIALECTS = frozenset({"postgresql", "oracle", "mysql", "mssql", "sqlite"})

TypeFactory = Callable[..., Any]
FunctionFactory = Callable[..., Any]


@dataclass
class DialectExtensions:
    custom_types: dict[str, TypeFactory] = field(default_factory=dict)
    functions: dict[str, FunctionFactory] = field(default_factory=dict)


_EXTENSIONS: dict[str, DialectExtensions] = {}


def get_extensions(dialect: str) -> DialectExtensions:
    dialect_name = dialect.strip().lower()
    if dialect_name not in SUPPORTED_DIALECTS:
        supported = ", ".join(sorted(SUPPORTED_DIALECTS))
        raise ValueError(f"Unsupported dialect '{dialect}'. Supported dialects: {supported}")
    return _EXTENSIONS.setdefault(dialect_name, DialectExtensions())


def register_custom_type(dialect: str, name: str, factory: TypeFactory) -> None:
    extensions = get_extensions(dialect)
    extensions.custom_types[name.strip().lower()] = factory


def register_function(dialect: str, name: str, factory: FunctionFactory) -> None:
    extensions = get_extensions(dialect)
    extensions.functions[name.strip().lower()] = factory


def get_custom_type_factory(dialect: str, name: str) -> TypeFactory:
    extensions = get_extensions(dialect)
    normalized_name = name.strip().lower()
    try:
        return extensions.custom_types[normalized_name]
    except KeyError as exc:
        raise KeyError(f"Custom type '{name}' is not registered for dialect '{dialect}'") from exc


def get_function_factory(dialect: str, name: str) -> FunctionFactory:
    extensions = get_extensions(dialect)
    normalized_name = name.strip().lower()
    try:
        return extensions.functions[normalized_name]
    except KeyError as exc:
        raise KeyError(f"Function '{name}' is not registered for dialect '{dialect}'") from exc


def build_custom_type(dialect: str, name: str, *args: Any, **kwargs: Any) -> Any:
    factory = get_custom_type_factory(dialect, name)
    return factory(*args, **kwargs)


def call_dialect_function(dialect: str, name: str, *args: Any, **kwargs: Any) -> Any:
    factory = get_function_factory(dialect, name)
    return factory(*args, **kwargs)


def list_custom_types(dialect: str) -> list[str]:
    extensions = get_extensions(dialect)
    return sorted(extensions.custom_types)


def list_functions(dialect: str) -> list[str]:
    extensions = get_extensions(dialect)
    return sorted(extensions.functions)


class DialectFunctionNamespace:
    """Convenience accessor for dialect-specific SQL function factories."""

    def __init__(self, dialect: str):
        self._dialect = dialect

    def __getattr__(self, name: str) -> FunctionFactory:
        return get_function_factory(self._dialect, name)

    def list(self) -> list[str]:
        return list_functions(self._dialect)
