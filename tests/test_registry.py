from __future__ import annotations

from pathlib import Path

import pytest

from sqltoolkit.connection import EngineRegistry, get_engine_from_file


@pytest.fixture(autouse=True)
def _dispose_registry() -> None:
    EngineRegistry.dispose_all()
    yield
    EngineRegistry.dispose_all()


@pytest.mark.unit
def test_sqlite_session_settings_are_applied_on_connect(tmp_path: Path) -> None:
    db_path = tmp_path / "app.db"
    config_path = tmp_path / "sqlite.ini"
    config_path.write_text(
        "\n".join(
            [
                "[databases.sqlite.default.readwrite]",
                f"file_path = {db_path}",
                "",
                "[databases.sqlite.default.readwrite.session_settings]",
                "foreign_keys = true",
                "busy_timeout = 5000",
            ]
        ),
        encoding="utf-8",
    )

    engine = get_engine_from_file(
        dialect="sqlite",
        tenant="default",
        access_mode="readwrite",
        config_path=str(config_path),
    )

    with engine.connect() as connection:
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()

    assert foreign_keys == 1
    assert busy_timeout == 5000


@pytest.mark.unit
def test_registry_key_reuse_with_different_session_settings_raises() -> None:
    EngineRegistry.get_engine(
        key="sqlite-default",
        dialect="sqlite",
        db_url="sqlite+pysqlite:///:memory:",
        session_settings={"foreign_keys": True},
    )

    with pytest.raises(ValueError, match="already registered with different settings"):
        EngineRegistry.get_engine(
            key="sqlite-default",
            dialect="sqlite",
            db_url="sqlite+pysqlite:///:memory:",
            session_settings={"foreign_keys": False},
        )


@pytest.mark.unit
def test_registry_reuses_and_disposes_sync_engines() -> None:
    first = EngineRegistry.get_engine(
        key="sqlite-cache",
        dialect="sqlite",
        db_url="sqlite+pysqlite:///:memory:",
    )
    second = EngineRegistry.get_engine(
        key="sqlite-cache",
        dialect="sqlite",
        db_url="sqlite+pysqlite:///:memory:",
    )

    assert first is second
    assert EngineRegistry.get_registry_size() == 1
    assert EngineRegistry.dispose_engine(key="sqlite-cache") is True
    assert EngineRegistry.dispose_engine(key="sqlite-cache") is False


@pytest.mark.unit
def test_registry_stats_and_eviction_behavior() -> None:
    EngineRegistry.set_max_entries(1)
    before = EngineRegistry.get_registry_stats()

    EngineRegistry.get_engine(
        key="sqlite-one",
        dialect="sqlite",
        db_url="sqlite+pysqlite:///:memory:",
    )
    EngineRegistry.get_engine(
        key="sqlite-two",
        dialect="sqlite",
        db_url="sqlite+pysqlite:///:memory:",
    )

    stats = EngineRegistry.get_registry_stats()
    keys = EngineRegistry.list_registry_keys()

    assert stats["creations"] - before["creations"] == 2
    assert stats["evictions"] - before["evictions"] == 1
    assert stats["size"] == 1
    assert keys == ["registry:sqlite-two:readwrite:sync"]


@pytest.mark.unit
def test_registry_exposes_engine_config_for_existing_entry() -> None:
    EngineRegistry.get_engine(
        key="sqlite-config",
        dialect="sqlite",
        db_url="sqlite+pysqlite:///:memory:",
        session_settings={"foreign_keys": True},
    )

    config = EngineRegistry.get_engine_config("registry:sqlite-config:readwrite:sync")

    assert config is not None
    assert config.url == "sqlite+pysqlite:///:memory:"
    assert config.on_connect_statements == ("PRAGMA foreign_keys = 1",)
