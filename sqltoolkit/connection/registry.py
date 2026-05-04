"""Thread-safe engine registry and public engine factories."""

from __future__ import annotations

from dataclasses import dataclass
from collections import OrderedDict
import os
from threading import RLock
import time
from typing import Any, Mapping, cast

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import (
    DEFAULT_ACCESS_MODE,
    EngineConfig,
    build_registry_key,
    build_named_registry_key,
    config_from_kwargs,
    load_config_from_env,
    load_config_from_file,
    normalize_access_mode,
)
from sqltoolkit.dialects import normalize_dialect


@dataclass(frozen=True)
class RegistryEntry:
    engine: Engine | AsyncEngine
    config: EngineConfig


@dataclass(frozen=True)
class FailureEntry:
    fingerprint: tuple[Any, ...]
    error: Exception
    expires_at: float


def _read_max_entries_from_env() -> int:
    raw_value = os.getenv("SQLTOOLKIT_REGISTRY_MAX_ENTRIES", "256")
    try:
        max_entries = int(raw_value)
    except ValueError:
        return 256
    return max_entries if max_entries > 0 else 256


def _read_failure_ttl_from_env() -> float:
    raw_value = os.getenv("SQLTOOLKIT_REGISTRY_FAILURE_TTL", "5")
    try:
        ttl_seconds = float(raw_value)
    except ValueError:
        return 5.0
    return ttl_seconds if ttl_seconds > 0 else 5.0


class EngineRegistry:
    """Global registry for sync and async SQLAlchemy engines."""

    _entries: OrderedDict[str, RegistryEntry] = OrderedDict()
    _failures: dict[str, FailureEntry] = {}
    _lock = RLock()
    _pid = os.getpid()
    _max_entries = _read_max_entries_from_env()
    _failure_ttl_seconds = _read_failure_ttl_from_env()
    _stats: dict[str, int] = {
        "hits": 0,
        "misses": 0,
        "evictions": 0,
        "failure_backoffs": 0,
        "creations": 0,
    }

    @classmethod
    def get_engine(
        cls,
        *,
        key: str,
        db_url: str | None = None,
        dialect: str | None = None,
        driver: str | None = None,
        access_mode: str = DEFAULT_ACCESS_MODE,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_pre_ping: bool = True,
        echo: bool = False,
        connect_args: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        engine_options: Mapping[str, Any] | None = None,
        session_settings: Mapping[str, Any] | None = None,
        **dialect_options: Any,
    ) -> Engine:
        cls._reset_if_forked()
        config = config_from_kwargs(
            dialect=dialect,
            db_url=db_url,
            driver=driver,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
            connect_args=connect_args,
            query=query,
            engine_options=engine_options,
            session_settings=session_settings,
            async_mode=False,
            **dialect_options,
        )
        return cls._get_or_create_sync_engine(
            key=build_named_registry_key(
                key=key,
                access_mode=normalize_access_mode(access_mode),
                async_mode=False,
            ),
            config=config,
        )

    @classmethod
    def get_async_engine(
        cls,
        *,
        key: str,
        db_url: str | None = None,
        dialect: str | None = None,
        driver: str | None = None,
        access_mode: str = DEFAULT_ACCESS_MODE,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_pre_ping: bool = True,
        echo: bool = False,
        connect_args: Mapping[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
        engine_options: Mapping[str, Any] | None = None,
        session_settings: Mapping[str, Any] | None = None,
        **dialect_options: Any,
    ) -> AsyncEngine:
        cls._reset_if_forked()
        config = config_from_kwargs(
            dialect=dialect,
            db_url=db_url,
            driver=driver,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
            connect_args=connect_args,
            query=query,
            engine_options=engine_options,
            session_settings=session_settings,
            async_mode=True,
            **dialect_options,
        )
        return cls._get_or_create_async_engine(
            key=build_named_registry_key(
                key=key,
                access_mode=normalize_access_mode(access_mode),
                async_mode=True,
            ),
            config=config,
        )

    @classmethod
    def dispose_all(cls) -> None:
        cls._reset_if_forked()
        with cls._lock:
            entries = list(cls._entries.values())
            cls._entries.clear()
            cls._failures.clear()

        for entry in entries:
            cls._dispose_entry(entry)

    @classmethod
    def dispose_engine(
        cls,
        *,
        key: str,
        access_mode: str = DEFAULT_ACCESS_MODE,
        async_mode: bool = False,
    ) -> bool:
        cls._reset_if_forked()
        registry_key = build_named_registry_key(
            key=key,
            access_mode=normalize_access_mode(access_mode),
            async_mode=async_mode,
        )
        return cls.dispose_registry_key(registry_key)

    @classmethod
    def dispose_registry_key(cls, registry_key: str) -> bool:
        cls._reset_if_forked()
        with cls._lock:
            entry = cls._entries.pop(registry_key, None)
            cls._failures.pop(registry_key, None)

        if entry is None:
            return False

        cls._dispose_entry(entry)
        return True

    @classmethod
    def list_registry_keys(cls) -> list[str]:
        cls._reset_if_forked()
        with cls._lock:
            return sorted(cls._entries)

    @classmethod
    def list_engines(cls) -> list[str]:
        return cls.list_registry_keys()

    @classmethod
    def get_registry_size(cls) -> int:
        cls._reset_if_forked()
        with cls._lock:
            return len(cls._entries)

    @classmethod
    def get_registry_stats(cls) -> dict[str, int]:
        cls._reset_if_forked()
        with cls._lock:
            return {
                "hits": cls._stats["hits"],
                "misses": cls._stats["misses"],
                "evictions": cls._stats["evictions"],
                "failure_backoffs": cls._stats["failure_backoffs"],
                "creations": cls._stats["creations"],
                "size": len(cls._entries),
                "max_entries": cls._max_entries,
            }

    @classmethod
    def get_engine_config(cls, registry_key: str) -> EngineConfig | None:
        cls._reset_if_forked()
        with cls._lock:
            entry = cls._entries.get(registry_key)
            if entry is not None:
                cls._entries.move_to_end(registry_key)
            return entry.config if entry is not None else None

    @classmethod
    def set_max_entries(cls, max_entries: int) -> None:
        cls._reset_if_forked()
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")

        evicted: list[RegistryEntry] = []
        with cls._lock:
            cls._max_entries = max_entries
            while len(cls._entries) > cls._max_entries:
                _, entry = cls._entries.popitem(last=False)
                evicted.append(entry)
            cls._stats["evictions"] += len(evicted)

        for entry in evicted:
            cls._dispose_entry(entry)

    @classmethod
    def _get_or_create_sync_engine(
        cls,
        *,
        key: str,
        config: EngineConfig,
    ) -> Engine:
        fingerprint = config.fingerprint()
        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                cls._assert_same_config(key=key, existing=existing, config=config)
                if cls._is_async_entry(existing):
                    raise ValueError(f"Registry key '{key}' is already registered as async")
                cls._stats["hits"] += 1
                cls._entries.move_to_end(key)
                return cast(Engine, existing.engine)
            cls._raise_if_failure_backoff_active(key=key, fingerprint=fingerprint)
            cls._stats["misses"] += 1

        try:
            engine = create_engine(**config.to_engine_kwargs())
            cls._configure_engine(engine, config)
        except Exception as exc:
            cls._record_failure(key=key, fingerprint=fingerprint, error=exc)
            raise

        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                cls._assert_same_config(key=key, existing=existing, config=config)
                if cls._is_async_entry(existing):
                    engine.dispose()
                    raise ValueError(f"Registry key '{key}' is already registered as async")
                engine.dispose()
                cls._stats["hits"] += 1
                cls._entries.move_to_end(key)
                return cast(Engine, existing.engine)

            cls._entries[key] = RegistryEntry(engine=engine, config=config)
            cls._failures.pop(key, None)
            cls._stats["creations"] += 1
            cls._entries.move_to_end(key)
            evicted = cls._evict_if_needed_locked(exclude_key=key)
            cls._stats["evictions"] += len(evicted)

        for entry in evicted:
            cls._dispose_entry(entry)
        return engine

    @classmethod
    def _get_or_create_async_engine(
        cls,
        *,
        key: str,
        config: EngineConfig,
    ) -> AsyncEngine:
        fingerprint = config.fingerprint()
        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                cls._assert_same_config(key=key, existing=existing, config=config)
                if not cls._is_async_entry(existing):
                    raise ValueError(f"Registry key '{key}' is already registered as sync")
                cls._stats["hits"] += 1
                cls._entries.move_to_end(key)
                return cast(AsyncEngine, existing.engine)
            cls._raise_if_failure_backoff_active(key=key, fingerprint=fingerprint)
            cls._stats["misses"] += 1

        try:
            engine = create_async_engine(**config.to_engine_kwargs())
            cls._configure_engine(engine, config)
        except Exception as exc:
            cls._record_failure(key=key, fingerprint=fingerprint, error=exc)
            raise

        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                cls._assert_same_config(key=key, existing=existing, config=config)
                if not cls._is_async_entry(existing):
                    engine.sync_engine.dispose()
                    raise ValueError(f"Registry key '{key}' is already registered as sync")
                engine.sync_engine.dispose()
                cls._stats["hits"] += 1
                cls._entries.move_to_end(key)
                return cast(AsyncEngine, existing.engine)

            cls._entries[key] = RegistryEntry(engine=engine, config=config)
            cls._failures.pop(key, None)
            cls._stats["creations"] += 1
            cls._entries.move_to_end(key)
            evicted = cls._evict_if_needed_locked(exclude_key=key)
            cls._stats["evictions"] += len(evicted)

        for entry in evicted:
            cls._dispose_entry(entry)
        return engine

    @classmethod
    def _assert_same_config(
        cls,
        *,
        key: str,
        existing: RegistryEntry,
        config: EngineConfig,
    ) -> None:
        if existing.config.fingerprint() != config.fingerprint():
            raise ValueError(
                f"Engine key '{key}' is already registered with different settings"
            )

    @staticmethod
    def _dispose_entry(entry: RegistryEntry) -> None:
        if isinstance(entry.engine, AsyncEngine):
            # AsyncEngine.dispose() is awaitable; the sync_engine path provides
            # deterministic cleanup for synchronous registry operations.
            entry.engine.sync_engine.dispose()
            return
        entry.engine.dispose()

    @staticmethod
    def _is_async_entry(entry: RegistryEntry) -> bool:
        return isinstance(entry.engine, AsyncEngine)

    @staticmethod
    def _configure_engine(engine: Engine | AsyncEngine, config: EngineConfig) -> None:
        if not config.on_connect_statements:
            return

        target = engine.sync_engine if isinstance(engine, AsyncEngine) else engine
        statements = config.on_connect_statements

        def run_session_setup(dbapi_connection: Any, connection_record: Any) -> None:
            del connection_record
            cursor = dbapi_connection.cursor()
            try:
                for statement in statements:
                    cursor.execute(statement)
            finally:
                cursor.close()

        event.listen(target, "connect", run_session_setup)

    @classmethod
    def _reset_if_forked(cls) -> None:
        current_pid = os.getpid()
        if current_pid == cls._pid:
            return

        with cls._lock:
            if current_pid == cls._pid:
                return
            entries = list(cls._entries.values())
            cls._entries.clear()
            cls._failures.clear()
            cls._pid = current_pid

        for entry in entries:
            cls._dispose_entry(entry)

    @classmethod
    def _evict_if_needed_locked(cls, *, exclude_key: str) -> list[RegistryEntry]:
        evicted: list[RegistryEntry] = []
        while len(cls._entries) > cls._max_entries:
            oldest_key, oldest_entry = cls._entries.popitem(last=False)
            if oldest_key == exclude_key:
                cls._entries[oldest_key] = oldest_entry
                cls._entries.move_to_end(oldest_key)
                continue
            evicted.append(oldest_entry)
        return evicted

    @classmethod
    def _raise_if_failure_backoff_active(
        cls,
        *,
        key: str,
        fingerprint: tuple[Any, ...],
    ) -> None:
        failure = cls._failures.get(key)
        if failure is None:
            return
        if failure.fingerprint != fingerprint:
            cls._failures.pop(key, None)
            return
        if failure.expires_at <= time.monotonic():
            cls._failures.pop(key, None)
            return
        cls._stats["failure_backoffs"] += 1
        raise failure.error

    @classmethod
    def _record_failure(
        cls,
        *,
        key: str,
        fingerprint: tuple[Any, ...],
        error: Exception,
    ) -> None:
        with cls._lock:
            cls._failures[key] = FailureEntry(
                fingerprint=fingerprint,
                error=error,
                expires_at=time.monotonic() + cls._failure_ttl_seconds,
            )


def _get_env_engine(
    *,
    dialect: str,
    tenant: str,
    access_mode: str,
    async_mode: bool,
    env: Mapping[str, str] | None,
) -> Engine | AsyncEngine:
    EngineRegistry._reset_if_forked()
    dialect_name = normalize_dialect(dialect)
    config = load_config_from_env(
        dialect=dialect_name,
        tenant=tenant,
        access_mode=access_mode,
        async_mode=async_mode,
        env=env,
    )
    registry_key = build_registry_key(
        dialect=dialect_name,
        tenant=tenant,
        access_mode=access_mode,
        async_mode=async_mode,
    )
    if async_mode:
        return EngineRegistry._get_or_create_async_engine(key=registry_key, config=config)
    return EngineRegistry._get_or_create_sync_engine(key=registry_key, config=config)


def _get_file_engine(
    *,
    dialect: str,
    tenant: str,
    config_path: str,
    access_mode: str,
    async_mode: bool,
) -> Engine | AsyncEngine:
    EngineRegistry._reset_if_forked()
    dialect_name = normalize_dialect(dialect)
    config = load_config_from_file(
        dialect=dialect_name,
        tenant=tenant,
        access_mode=access_mode,
        async_mode=async_mode,
        config_path=config_path,
    )
    registry_key = build_registry_key(
        dialect=dialect_name,
        tenant=tenant,
        access_mode=access_mode,
        async_mode=async_mode,
    )
    if async_mode:
        return EngineRegistry._get_or_create_async_engine(key=registry_key, config=config)
    return EngineRegistry._get_or_create_sync_engine(key=registry_key, config=config)


def get_engine(
    *,
    dialect: str,
    tenant: str = "default",
    access_mode: str = DEFAULT_ACCESS_MODE,
    env: Mapping[str, str] | None = None,
) -> Engine:
    return cast(
        Engine,
        _get_env_engine(
            dialect=dialect,
            tenant=tenant,
            access_mode=access_mode,
            async_mode=False,
            env=env,
        ),
    )


def get_async_engine(
    *,
    dialect: str,
    tenant: str = "default",
    access_mode: str = DEFAULT_ACCESS_MODE,
    env: Mapping[str, str] | None = None,
) -> AsyncEngine:
    return cast(
        AsyncEngine,
        _get_env_engine(
            dialect=dialect,
            tenant=tenant,
            access_mode=access_mode,
            async_mode=True,
            env=env,
        ),
    )


def get_engine_from_file(
    *,
    dialect: str,
    tenant: str = "default",
    config_path: str,
    access_mode: str = DEFAULT_ACCESS_MODE,
) -> Engine:
    return cast(
        Engine,
        _get_file_engine(
            dialect=dialect,
            tenant=tenant,
            config_path=config_path,
            access_mode=access_mode,
            async_mode=False,
        ),
    )


def get_async_engine_from_file(
    *,
    dialect: str,
    tenant: str = "default",
    config_path: str,
    access_mode: str = DEFAULT_ACCESS_MODE,
) -> AsyncEngine:
    return cast(
        AsyncEngine,
        _get_file_engine(
            dialect=dialect,
            tenant=tenant,
            config_path=config_path,
            access_mode=access_mode,
            async_mode=True,
        ),
    )
