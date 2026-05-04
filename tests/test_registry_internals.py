from __future__ import annotations

import types

import pytest

import sqltoolkit.connection.registry as registry_module
from sqltoolkit.connection.config import EngineConfig
from sqltoolkit.connection.registry import (
    EngineRegistry,
    FailureEntry,
    RegistryEntry,
    _get_env_engine,
    _get_file_engine,
    _read_failure_ttl_from_env,
    _read_max_entries_from_env,
    get_async_engine,
    get_async_engine_from_file,
    get_engine,
)


class DummySyncEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class DummyAsyncEngine:
    def __init__(self) -> None:
        self.sync_engine = DummySyncEngine()


@pytest.fixture(autouse=True)
def _reset_registry_state(monkeypatch: pytest.MonkeyPatch) -> None:
    EngineRegistry.dispose_all()
    EngineRegistry._entries.clear()
    EngineRegistry._failures.clear()
    EngineRegistry._stats = {
        "hits": 0,
        "misses": 0,
        "evictions": 0,
        "failure_backoffs": 0,
        "creations": 0,
    }
    EngineRegistry._max_entries = 256
    EngineRegistry._failure_ttl_seconds = 5.0
    yield
    EngineRegistry.dispose_all()


@pytest.mark.unit
def test_registry_env_numeric_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLTOOLKIT_REGISTRY_MAX_ENTRIES", "bad")
    assert _read_max_entries_from_env() == 256
    monkeypatch.setenv("SQLTOOLKIT_REGISTRY_MAX_ENTRIES", "-1")
    assert _read_max_entries_from_env() == 256
    monkeypatch.setenv("SQLTOOLKIT_REGISTRY_FAILURE_TTL", "bad")
    assert _read_failure_ttl_from_env() == 5.0
    monkeypatch.setenv("SQLTOOLKIT_REGISTRY_FAILURE_TTL", "-1")
    assert _read_failure_ttl_from_env() == 5.0


@pytest.mark.unit
def test_configure_engine_registers_event(monkeypatch: pytest.MonkeyPatch) -> None:
    listened: list[tuple[object, str, object]] = []

    def fake_listen(target: object, event_name: str, fn: object) -> None:
        listened.append((target, event_name, fn))

    monkeypatch.setattr(registry_module.event, "listen", fake_listen)
    engine = DummySyncEngine()
    EngineRegistry._configure_engine(
        engine,
        EngineConfig(url="sqlite://", on_connect_statements=("PRAGMA foreign_keys = 1",)),
    )

    assert listened and listened[0][0] is engine and listened[0][1] == "connect"


@pytest.mark.unit
def test_configure_engine_uses_sync_engine_for_async(monkeypatch: pytest.MonkeyPatch) -> None:
    listened: list[object] = []
    monkeypatch.setattr(registry_module, "AsyncEngine", DummyAsyncEngine)
    monkeypatch.setattr(
        registry_module.event,
        "listen",
        lambda target, event_name, fn: listened.append(target),
    )
    engine = DummyAsyncEngine()
    EngineRegistry._configure_engine(
        engine,
        EngineConfig(url="sqlite://", on_connect_statements=("PRAGMA busy_timeout = 5000",)),
    )
    assert listened == [engine.sync_engine]


@pytest.mark.unit
def test_dispose_entry_handles_async_and_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "AsyncEngine", DummyAsyncEngine)
    sync_engine = DummySyncEngine()
    async_engine = DummyAsyncEngine()

    EngineRegistry._dispose_entry(RegistryEntry(engine=sync_engine, config=EngineConfig("x")))
    EngineRegistry._dispose_entry(RegistryEntry(engine=async_engine, config=EngineConfig("x")))

    assert sync_engine.disposed is True
    assert async_engine.sync_engine.disposed is True
    assert EngineRegistry._is_async_entry(RegistryEntry(engine=async_engine, config=EngineConfig("x")))
    assert not EngineRegistry._is_async_entry(RegistryEntry(engine=sync_engine, config=EngineConfig("x")))


@pytest.mark.unit
def test_set_max_entries_validation_and_getters() -> None:
    with pytest.raises(ValueError, match="max_entries must be > 0"):
        EngineRegistry.set_max_entries(0)
    assert EngineRegistry.get_engine_config("missing") is None
    assert EngineRegistry.dispose_registry_key("missing") is False
    assert EngineRegistry.list_engines() == []


@pytest.mark.unit
def test_failure_backoff_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    error = RuntimeError("boom")
    EngineRegistry._failures["k"] = FailureEntry(
        fingerprint=("a",),
        error=error,
        expires_at=registry_module.time.monotonic() + 10,
    )
    with pytest.raises(RuntimeError, match="boom"):
        EngineRegistry._raise_if_failure_backoff_active(key="k", fingerprint=("a",))
    assert EngineRegistry.get_registry_stats()["failure_backoffs"] == 1

    EngineRegistry._raise_if_failure_backoff_active(key="k", fingerprint=("b",))
    assert "k" not in EngineRegistry._failures

    EngineRegistry._failures["k"] = FailureEntry(
        fingerprint=("a",),
        error=error,
        expires_at=registry_module.time.monotonic() - 1,
    )
    EngineRegistry._raise_if_failure_backoff_active(key="k", fingerprint=("a",))
    assert "k" not in EngineRegistry._failures


@pytest.mark.unit
def test_sync_creation_failure_records_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_create_engine(**kwargs: object) -> object:
        calls["count"] += 1
        raise RuntimeError("create failed")

    monkeypatch.setattr(registry_module, "create_engine", fake_create_engine)
    config = EngineConfig(url="sqlite://")

    with pytest.raises(RuntimeError, match="create failed"):
        EngineRegistry._get_or_create_sync_engine(key="k", config=config)
    with pytest.raises(RuntimeError, match="create failed"):
        EngineRegistry._get_or_create_sync_engine(key="k", config=config)

    assert calls["count"] == 1


@pytest.mark.unit
def test_async_creation_and_reuse_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "AsyncEngine", DummyAsyncEngine)
    monkeypatch.setattr(registry_module, "create_async_engine", lambda **kwargs: DummyAsyncEngine())
    monkeypatch.setattr(registry_module.event, "listen", lambda *args, **kwargs: None)

    config = EngineConfig(url="sqlite+aiosqlite://", on_connect_statements=("X",))
    engine = EngineRegistry._get_or_create_async_engine(key="ak", config=config)
    reused = EngineRegistry._get_or_create_async_engine(key="ak", config=config)

    assert engine is reused
    assert EngineRegistry.get_registry_stats()["hits"] == 1


@pytest.mark.unit
def test_async_registry_conflict_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry_module, "AsyncEngine", DummyAsyncEngine)
    monkeypatch.setattr(registry_module, "create_async_engine", lambda **kwargs: DummyAsyncEngine())
    monkeypatch.setattr(registry_module.event, "listen", lambda *args, **kwargs: None)

    async_config = EngineConfig("sqlite+aiosqlite://")
    sync_entry = RegistryEntry(engine=DummySyncEngine(), config=async_config)
    EngineRegistry._entries["k"] = sync_entry
    with pytest.raises(ValueError, match="already registered as sync"):
        EngineRegistry._get_or_create_async_engine(key="k", config=async_config)

    sync_config = EngineConfig("sqlite://")
    async_entry = RegistryEntry(engine=DummyAsyncEngine(), config=sync_config)
    EngineRegistry._entries.clear()
    EngineRegistry._entries["k"] = async_entry
    with pytest.raises(ValueError, match="already registered as async"):
        EngineRegistry._get_or_create_sync_engine(key="k", config=sync_config)


@pytest.mark.unit
def test_reset_if_forked_disposes_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    disposed: list[RegistryEntry] = []
    entry = RegistryEntry(engine=DummySyncEngine(), config=EngineConfig("sqlite://"))
    EngineRegistry._entries["k"] = entry
    EngineRegistry._pid = 100
    monkeypatch.setattr(registry_module.os, "getpid", lambda: 101)
    monkeypatch.setattr(EngineRegistry, "_dispose_entry", lambda e: disposed.append(e))

    EngineRegistry._reset_if_forked()

    assert disposed == [entry]
    assert EngineRegistry._entries == {}
    assert EngineRegistry._pid == 101


@pytest.mark.unit
def test_env_and_file_engine_wrappers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    config = EngineConfig(url="sqlite://")
    monkeypatch.setattr(registry_module, "load_config_from_env", lambda **kwargs: config)
    monkeypatch.setattr(registry_module, "load_config_from_file", lambda **kwargs: config)
    monkeypatch.setattr(EngineRegistry, "_get_or_create_sync_engine", lambda **kwargs: "SYNC")
    monkeypatch.setattr(EngineRegistry, "_get_or_create_async_engine", lambda **kwargs: "ASYNC")

    assert _get_env_engine(
        dialect="sqlite",
        tenant="default",
        access_mode="readwrite",
        async_mode=False,
        env={},
    ) == "SYNC"
    assert _get_env_engine(
        dialect="sqlite",
        tenant="default",
        access_mode="readwrite",
        async_mode=True,
        env={},
    ) == "ASYNC"
    assert _get_file_engine(
        dialect="sqlite",
        tenant="default",
        config_path=str(tmp_path / "x.ini"),
        access_mode="readwrite",
        async_mode=False,
    ) == "SYNC"
    assert get_engine(dialect="sqlite", env={}) == "SYNC"
    assert get_async_engine(dialect="sqlite", env={}) == "ASYNC"
    assert get_async_engine_from_file(dialect="sqlite", config_path="x.ini") == "ASYNC"
