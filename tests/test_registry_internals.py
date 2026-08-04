from __future__ import annotations

from importlib import import_module

import pytest

import sqltoolkit.connection._engine_base as base_module
import sqltoolkit.connection.registry as registry_module
from sqltoolkit.connection.config import EngineConfig
from sqltoolkit.connection.registry import (
    AsyncEngineRegistry,
    EngineRegistry,
    FailureEntry,
    RegistryEntry,
    SyncEngineRegistry,
    _get_env_engine,
    _get_file_engine,
    _read_failure_ttl_from_env,
    _read_max_entries_from_env,
    get_async_engine,
    get_async_engine_from_file,
    get_engine,
)
from sqltoolkit.connection.sync.session import SyncSessionRegistry

async_engine_module = import_module("sqltoolkit.connection.async.engine")
async_session_module = import_module("sqltoolkit.connection.async.session")
AsyncSessionRegistry = async_session_module.AsyncSessionRegistry


class DummySyncEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


class DummyAsyncEngine:
    def __init__(self) -> None:
        self.sync_engine = DummySyncEngine()


@pytest.fixture(autouse=True)
def _reset_registry_state() -> None:
    EngineRegistry.dispose_all()
    for registry in (SyncEngineRegistry, AsyncEngineRegistry):
        registry._entries.clear()
        registry._failures.clear()
        registry.reset_stats()
        registry._max_entries = 256
        registry._failure_ttl_seconds = 5.0
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

    monkeypatch.setattr(base_module.event, "listen", fake_listen)
    engine = DummySyncEngine()
    SyncEngineRegistry._configure_engine(
        engine,
        EngineConfig(url="sqlite://", on_connect_statements=("PRAGMA foreign_keys = 1",)),
    )

    assert listened and listened[0][0] is engine and listened[0][1] == "connect"


@pytest.mark.unit
def test_configure_engine_uses_sync_engine_for_async(monkeypatch: pytest.MonkeyPatch) -> None:
    listened: list[object] = []
    monkeypatch.setattr(base_module, "AsyncEngine", DummyAsyncEngine)
    monkeypatch.setattr(
        base_module.event,
        "listen",
        lambda target, event_name, fn: listened.append(target),
    )
    engine = DummyAsyncEngine()
    AsyncEngineRegistry._configure_engine(
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
def test_failure_backoff_and_expiry() -> None:
    error = RuntimeError("boom")
    SyncEngineRegistry._failures["k"] = FailureEntry(
        fingerprint=("a",),
        error=error,
        expires_at=base_module.time.monotonic() + 10,
    )
    with pytest.raises(RuntimeError, match="boom"):
        SyncEngineRegistry._raise_if_failure_backoff_active(key="k", fingerprint=("a",))
    assert SyncEngineRegistry.get_registry_stats()["failure_backoffs"] == 1

    SyncEngineRegistry._raise_if_failure_backoff_active(key="k", fingerprint=("b",))
    assert "k" not in SyncEngineRegistry._failures

    SyncEngineRegistry._failures["k"] = FailureEntry(
        fingerprint=("a",),
        error=error,
        expires_at=base_module.time.monotonic() - 1,
    )
    SyncEngineRegistry._raise_if_failure_backoff_active(key="k", fingerprint=("a",))
    assert "k" not in SyncEngineRegistry._failures


@pytest.mark.unit
def test_sync_creation_failure_records_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def fake_create_engine(**kwargs: object) -> object:
        calls["count"] += 1
        raise RuntimeError("create failed")

    monkeypatch.setattr("sqltoolkit.connection.sync.engine.create_engine", fake_create_engine)
    config = EngineConfig(url="sqlite://")

    with pytest.raises(RuntimeError, match="create failed"):
        SyncEngineRegistry.get_or_create(key="k", config=config)
    with pytest.raises(RuntimeError, match="create failed"):
        SyncEngineRegistry.get_or_create(key="k", config=config)

    assert calls["count"] == 1


@pytest.mark.unit
def test_async_creation_and_reuse_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "AsyncEngine", DummyAsyncEngine)
    monkeypatch.setattr(async_engine_module, "create_async_engine", lambda **kwargs: DummyAsyncEngine())
    monkeypatch.setattr(base_module.event, "listen", lambda *args, **kwargs: None)

    config = EngineConfig(url="sqlite+aiosqlite://", on_connect_statements=("X",))
    engine = AsyncEngineRegistry.get_or_create(key="ak", config=config)
    reused = AsyncEngineRegistry.get_or_create(key="ak", config=config)

    assert engine is reused
    assert AsyncEngineRegistry.get_registry_stats()["hits"] == 1


@pytest.mark.unit
def test_sync_and_async_engine_registries_are_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_module, "AsyncEngine", DummyAsyncEngine)
    monkeypatch.setattr(async_engine_module, "create_async_engine", lambda **kwargs: DummyAsyncEngine())
    monkeypatch.setattr(base_module.event, "listen", lambda *args, **kwargs: None)

    sync_config = EngineConfig("sqlite://")
    async_config = EngineConfig("sqlite+aiosqlite://")
    sync_engine = SyncEngineRegistry.get_or_create(key="same", config=sync_config)
    async_engine = AsyncEngineRegistry.get_or_create(key="same", config=async_config)

    assert sync_engine is not async_engine
    assert SyncEngineRegistry.list_registry_keys() == ["same"]
    assert AsyncEngineRegistry.list_registry_keys() == ["same"]


@pytest.mark.unit
def test_reset_if_forked_disposes_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    disposed: list[RegistryEntry] = []
    entry = RegistryEntry(engine=DummySyncEngine(), config=EngineConfig("sqlite://"))
    SyncEngineRegistry._entries["k"] = entry
    SyncEngineRegistry._pid = 100
    monkeypatch.setattr(base_module.os, "getpid", lambda: 101)
    monkeypatch.setattr(SyncEngineRegistry, "_dispose_entry", lambda e: disposed.append(e))

    SyncEngineRegistry._reset_if_forked()

    assert disposed == [entry]
    assert SyncEngineRegistry._entries == {}
    assert SyncEngineRegistry._pid == 101


@pytest.mark.unit
def test_env_and_file_engine_wrappers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    config = EngineConfig(url="sqlite://")
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(registry_module, "load_config_from_env", lambda **kwargs: config)
    monkeypatch.setattr(registry_module, "load_config_from_file", lambda **kwargs: config)
    monkeypatch.setattr(
        SyncEngineRegistry,
        "get_or_create",
        lambda **kwargs: calls.append(kwargs) or "SYNC",
    )
    monkeypatch.setattr(AsyncEngineRegistry, "get_or_create", lambda **kwargs: "ASYNC")

    assert _get_env_engine(
        dialect="sqlite",
        tenant="default",
        access_mode=" Reporting ",
        async_mode=False,
        env={},
    ) == "SYNC"
    assert calls[-1]["key"] == "sqlite:default:reporting:sync"
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


@pytest.mark.unit
def test_sync_session_registry_reuses_and_rejects_conflicts() -> None:
    first_engine = DummySyncEngine()
    second_engine = DummySyncEngine()

    first = SyncSessionRegistry.get_sessionmaker(key="s", engine=first_engine, expire_on_commit=False)
    second = SyncSessionRegistry.get_sessionmaker(key="s", engine=first_engine, expire_on_commit=False)

    assert first is second
    with pytest.raises(ValueError, match="different settings"):
        SyncSessionRegistry.get_sessionmaker(key="s", engine=second_engine, expire_on_commit=False)
    assert SyncSessionRegistry.dispose_registry_key("s") is True
    assert SyncSessionRegistry.dispose_registry_key("s") is False


@pytest.mark.unit
def test_async_session_registry_reuses_and_rejects_conflicts() -> None:
    first_engine = DummyAsyncEngine()
    second_engine = DummyAsyncEngine()

    first = AsyncSessionRegistry.get_sessionmaker(key="a", engine=first_engine, expire_on_commit=False)
    second = AsyncSessionRegistry.get_sessionmaker(key="a", engine=first_engine, expire_on_commit=False)

    assert first is second
    with pytest.raises(ValueError, match="different settings"):
        AsyncSessionRegistry.get_sessionmaker(key="a", engine=second_engine, expire_on_commit=False)
    assert AsyncSessionRegistry.dispose_registry_key("a") is True
    assert AsyncSessionRegistry.dispose_registry_key("a") is False
