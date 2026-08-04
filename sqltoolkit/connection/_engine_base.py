"""Shared engine registry primitives."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import os
from threading import RLock
import time
from typing import Any, Generic, TypeVar

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import EngineConfig

EngineT = TypeVar("EngineT", Engine, AsyncEngine)


@dataclass(frozen=True)
class RegistryEntry(Generic[EngineT]):
    engine: EngineT
    config: EngineConfig


@dataclass(frozen=True)
class FailureEntry:
    fingerprint: tuple[Any, ...]
    error: Exception
    expires_at: float


def read_max_entries_from_env() -> int:
    raw_value = os.getenv("SQLTOOLKIT_REGISTRY_MAX_ENTRIES", "256")
    try:
        max_entries = int(raw_value)
    except ValueError:
        return 256
    return max_entries if max_entries > 0 else 256


def read_failure_ttl_from_env() -> float:
    raw_value = os.getenv("SQLTOOLKIT_REGISTRY_FAILURE_TTL", "5")
    try:
        ttl_seconds = float(raw_value)
    except ValueError:
        return 5.0
    return ttl_seconds if ttl_seconds > 0 else 5.0


class BaseEngineRegistry(Generic[EngineT]):
    """Process-local LRU registry for one engine interface."""

    _entries: OrderedDict[str, RegistryEntry[EngineT]] = OrderedDict()
    _failures: dict[str, FailureEntry] = {}
    _lock = RLock()
    _pid = os.getpid()
    _max_entries = read_max_entries_from_env()
    _failure_ttl_seconds = read_failure_ttl_from_env()
    _stats: dict[str, int] = {
        "hits": 0,
        "misses": 0,
        "evictions": 0,
        "failure_backoffs": 0,
        "creations": 0,
    }

    @classmethod
    def get_or_create(cls, *, key: str, config: EngineConfig) -> EngineT:
        cls._reset_if_forked()
        fingerprint = config.fingerprint()
        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                cls._assert_same_config(key=key, existing=existing, config=config)
                cls._stats["hits"] += 1
                cls._entries.move_to_end(key)
                return existing.engine
            cls._raise_if_failure_backoff_active(key=key, fingerprint=fingerprint)
            cls._stats["misses"] += 1

        try:
            engine = cls._create_engine(config)
            cls._configure_engine(engine, config)
        except Exception as exc:
            cls._record_failure(key=key, fingerprint=fingerprint, error=exc)
            raise

        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                cls._assert_same_config(key=key, existing=existing, config=config)
                cls._dispose_engine(engine)
                cls._stats["hits"] += 1
                cls._entries.move_to_end(key)
                return existing.engine

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
    def dispose_all(cls) -> None:
        cls._reset_if_forked()
        with cls._lock:
            entries = list(cls._entries.values())
            cls._entries.clear()
            cls._failures.clear()

        for entry in entries:
            cls._dispose_entry(entry)

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

        evicted: list[RegistryEntry[EngineT]] = []
        with cls._lock:
            cls._max_entries = max_entries
            while len(cls._entries) > cls._max_entries:
                _, entry = cls._entries.popitem(last=False)
                evicted.append(entry)
            cls._stats["evictions"] += len(evicted)

        for entry in evicted:
            cls._dispose_entry(entry)

    @classmethod
    def reset_stats(cls) -> None:
        with cls._lock:
            cls._stats = {
                "hits": 0,
                "misses": 0,
                "evictions": 0,
                "failure_backoffs": 0,
                "creations": 0,
            }

    @classmethod
    def _assert_same_config(
        cls,
        *,
        key: str,
        existing: RegistryEntry[EngineT],
        config: EngineConfig,
    ) -> None:
        if existing.config.fingerprint() != config.fingerprint():
            raise ValueError(
                f"Engine key '{key}' is already registered with different settings"
            )

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
    def _evict_if_needed_locked(cls, *, exclude_key: str) -> list[RegistryEntry[EngineT]]:
        evicted: list[RegistryEntry[EngineT]] = []
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

    @classmethod
    def _dispose_entry(cls, entry: RegistryEntry[EngineT]) -> None:
        cls._dispose_engine(entry.engine)

    @staticmethod
    def _create_engine(config: EngineConfig) -> EngineT:
        raise NotImplementedError

    @staticmethod
    def _dispose_engine(engine: EngineT) -> None:
        raise NotImplementedError
