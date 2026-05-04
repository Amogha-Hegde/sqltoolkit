from __future__ import annotations

import pytest

from sqltoolkit.connection.config import build_engine_config
from sqltoolkit.dialects import build_session_statements


@pytest.mark.unit
@pytest.mark.parametrize(
    ("dialect", "settings", "expected"),
    [
        (
            "postgresql",
            {"search_path": "app, public", "jit": False},
            [
                "SELECT pg_catalog.set_config('search_path', 'app, public', false)",
                "SELECT pg_catalog.set_config('jit', 'off', false)",
            ],
        ),
        (
            "mysql",
            {"sql_mode": "STRICT_ALL_TABLES", "transaction_read_only": 1},
            ["SET SESSION sql_mode = 'STRICT_ALL_TABLES', SESSION transaction_read_only = 1"],
        ),
        (
            "oracle",
            {"time_zone": "UTC", "optimizer_mode": "FIRST_ROWS"},
            [
                "ALTER SESSION SET time_zone = 'UTC'",
                "ALTER SESSION SET optimizer_mode = 'FIRST_ROWS'",
            ],
        ),
        (
            "mssql",
            {"LOCK_TIMEOUT": 5000, "TRANSACTION ISOLATION LEVEL": "READ COMMITTED"},
            [
                "SET LOCK_TIMEOUT 5000",
                "SET TRANSACTION ISOLATION LEVEL READ COMMITTED",
            ],
        ),
        (
            "sqlite",
            {"foreign_keys": True, "busy_timeout": 5000},
            [
                "PRAGMA foreign_keys = 1",
                "PRAGMA busy_timeout = 5000",
            ],
        ),
    ],
)
def test_build_session_statements_for_supported_backends(
    dialect: str,
    settings: dict[str, object],
    expected: list[str],
) -> None:
    assert build_session_statements(dialect=dialect, settings=settings) == expected


@pytest.mark.unit
def test_invalid_session_setting_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported postgresql session setting name"):
        build_session_statements(
            dialect="postgresql",
            settings={"search_path;drop schema public": "app"},
        )


@pytest.mark.unit
def test_build_engine_config_separates_database_engine_and_session_settings() -> None:
    config = build_engine_config(
        dialect="postgresql",
        async_mode=False,
        raw_config={
            "db_url": "postgresql+psycopg://user:password@localhost:5432/app",
            "database_options": {"application_name": "sqltoolkit"},
            "engine_options": {"pool_recycle": 1800, "pool_use_lifo": True},
            "session_settings": {"search_path": "app, public"},
        },
    )

    assert config.url.endswith("?application_name=sqltoolkit")
    assert config.engine_kwargs == {"pool_recycle": 1800, "pool_use_lifo": True}
    assert config.on_connect_statements == (
        "SELECT pg_catalog.set_config('search_path', 'app, public', false)",
    )
