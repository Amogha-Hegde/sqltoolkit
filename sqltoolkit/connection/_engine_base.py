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
from . import failure_backend

EngineT = TypeVar("EngineT", Engine, AsyncEngine)


@dataclass(frozen=True)
class RegistryEntry(Generic[EngineT]):
    """Cached engine and its normalized configuration."""

    engine: EngineT
    config: EngineConfig


@dataclass(frozen=True)
class FailureEntry:
    """Cached engine creation failure used for short backoff windows."""

    fingerprint: tuple[Any, ...]
    error: Exception
    expires_at: float


def read_max_entries_from_env() -> int:
    """Read the registry size limit from SQLTOOLKIT_REGISTRY_MAX_ENTRIES."""
    raw_value = os.getenv("SQLTOOLKIT_REGISTRY_MAX_ENTRIES", "256")
    try:
        max_entries = int(raw_value)
    except ValueError:
        return 256
    return max_entries if max_entries > 0 else 256


def read_failure_ttl_from_env() -> float:
    """Read the failure backoff TTL from SQLTOOLKIT_REGISTRY_FAILURE_TTL."""
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
        """Return an existing engine or create and cache a new one."""
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
        with cls._lock:
            cls._stats["misses"] += 1

        try:
            engine = cls._create_engine(config)
            cls._configure_engine(engine, config, key=key)
        except Exception as exc:
            cls._record_failure(key=key, fingerprint=fingerprint, error=exc)
            raise

        cls._delete_failure(key)
        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                cls._assert_same_config(key=key, existing=existing, config=config)
                cls._dispose_engine(engine)
                cls._stats["hits"] += 1
                cls._entries.move_to_end(key)
                return existing.engine

            cls._entries[key] = RegistryEntry(engine=engine, config=config)
            cls._stats["creations"] += 1
            cls._entries.move_to_end(key)
            evicted = cls._evict_if_needed_locked(exclude_key=key)
            cls._stats["evictions"] += len(evicted)

        for entry in evicted:
            cls._dispose_entry(entry)
        return engine

    @classmethod
    def dispose_all(cls) -> None:
        """Dispose every cached engine and clear failure backoffs."""
        cls._reset_if_forked()
        with cls._lock:
            entries = list(cls._entries.values())
            cls._entries.clear()

        cls._clear_failures()

        for entry in entries:
            cls._dispose_entry(entry)

    @classmethod
    def dispose_registry_key(cls, registry_key: str) -> bool:
        """Dispose and remove one cached engine by full registry key."""
        cls._reset_if_forked()
        with cls._lock:
            entry = cls._entries.pop(registry_key, None)

        cls._delete_failure(registry_key)

        if entry is None:
            return False

        cls._dispose_entry(entry)
        return True

    @classmethod
    def list_registry_keys(cls) -> list[str]:
        """Return all cached engine registry keys."""
        cls._reset_if_forked()
        with cls._lock:
            return sorted(cls._entries)

    @classmethod
    def get_registry_size(cls) -> int:
        """Return the number of cached engines."""
        cls._reset_if_forked()
        with cls._lock:
            return len(cls._entries)

    @classmethod
    def get_registry_stats(cls) -> dict[str, int]:
        """Return registry counters and current cache size."""
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
        """Return cached engine config and mark the entry recently used."""
        cls._reset_if_forked()
        with cls._lock:
            entry = cls._entries.get(registry_key)
            if entry is not None:
                cls._entries.move_to_end(registry_key)
            return entry.config if entry is not None else None

    @classmethod
    def set_max_entries(cls, max_entries: int) -> None:
        """Set the cache size limit and evict oldest entries if needed."""
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
        """Reset registry counters without changing cached engines."""
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
        """Reject reuse of a key with different normalized config."""
        if existing.config.fingerprint() != config.fingerprint():
            raise ValueError(
                f"Engine key '{key}' is already registered with different settings"
            )

    @classmethod
    def _configure_engine(
        cls,
        engine: Engine | AsyncEngine,
        config: EngineConfig,
        *,
        key: str | None = None,
    ) -> None:
        """Attach session setup SQL to each new DBAPI connection."""
        target = engine.sync_engine if isinstance(engine, AsyncEngine) else engine
        statements = config.on_connect_statements

        if key is not None and hasattr(target, "dialect"):
            fingerprint = config.fingerprint()

            def check_connection_backoff(
                dialect: Any,
                connection_record: Any,
                cargs: Any,
                cparams: Any,
            ) -> None:
                """Skip a new DBAPI connection while its failure is backed off."""
                del dialect, connection_record, cargs, cparams
                cls._raise_if_failure_backoff_active(
                    key=key,
                    fingerprint=fingerprint,
                )

            def record_connection_failure(exception_context: Any) -> None:
                """Cache failures raised while SQLAlchemy establishes a connection."""
                if exception_context.connection is None:
                    error = exception_context.original_exception
                    if isinstance(error, Exception):
                        cls._record_failure(
                            key=key,
                            fingerprint=fingerprint,
                            error=error,
                        )

            def clear_connection_failure(dbapi_connection: Any, connection_record: Any) -> None:
                """Clear a backoff after a DBAPI connection succeeds."""
                del dbapi_connection, connection_record
                cls._delete_failure(key)

            event.listen(target.dialect, "do_connect", check_connection_backoff)
            event.listen(target, "handle_error", record_connection_failure)
            event.listen(target, "connect", clear_connection_failure)

        if not statements:
            return

        def run_session_setup(dbapi_connection: Any, connection_record: Any) -> None:
            """Run configured setup SQL for one DBAPI connection."""
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
        """Clear inherited engine objects after process forks."""
        current_pid = os.getpid()
        if current_pid == cls._pid:
            return

        with cls._lock:
            if current_pid == cls._pid:
                return
            entries = list(cls._entries.values())
            cls._entries.clear()
            cls._pid = current_pid

        with cls._lock:
            cls._failures.clear()
        for entry in entries:
            cls._dispose_entry(entry)

    @classmethod
    def _evict_if_needed_locked(cls, *, exclude_key: str) -> list[RegistryEntry[EngineT]]:
        """Evict least-recently-used entries while holding the registry lock."""
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
        """Raise a cached creation error while its backoff window is active."""
        failure = cls._read_failure(key)
        if failure is None:
            return
        fingerprint_text = repr(fingerprint)
        if failure["fingerprint"] != fingerprint_text:
            cls._delete_failure(key)
            return
        with cls._lock:
            cls._stats["failure_backoffs"] += 1
        if "error" in failure:
            raise failure["error"]
        raise RuntimeError(
            "Cached database connection failure: "
            f"{failure['error_type']}: {failure['message']}"
        )

    @classmethod
    def _record_failure(
        cls,
        *,
        key: str,
        fingerprint: tuple[Any, ...],
        error: Exception,
    ) -> None:
        """Store an engine creation failure for short-term backoff."""
        if failure_backend.get_failure_backend_name() == "memory":
            with cls._lock:
                cls._failures[key] = FailureEntry(
                    fingerprint=fingerprint,
                    error=error,
                    expires_at=time.monotonic() + cls._failure_ttl_seconds,
                )
            return
        record = {
            "fingerprint": repr(fingerprint),
            "error_type": type(error).__name__,
            "message": str(error),
        }
        try:
            failure_backend.write_failure(cls.__name__, key, record, cls._failure_ttl_seconds)
        except Exception:
            # Preserve backoff locally if shared storage is unavailable.
            with cls._lock:
                cls._failures[key] = FailureEntry(
                    fingerprint=fingerprint,
                    error=error,
                    expires_at=time.monotonic() + cls._failure_ttl_seconds,
                )

    @classmethod
    def _read_failure(cls, key: str) -> dict[str, Any] | None:
        """Read failure metadata from the selected backend."""
        if failure_backend.get_failure_backend_name() == "memory":
            with cls._lock:
                failure = cls._failures.get(key)
                if failure is None:
                    return None
                if failure.expires_at <= time.monotonic():
                    cls._failures.pop(key, None)
                    return None
                return {
                    "fingerprint": repr(failure.fingerprint),
                    "error": failure.error,
                }
        try:
            shared_failure = failure_backend.read_failure(cls.__name__, key)
        except Exception:
            shared_failure = None
        if shared_failure is not None:
            return shared_failure

        # Local entries are also checked when Redis is healthy, since they may
        # have been recorded during a previous Redis outage.
        with cls._lock:
            failure = cls._failures.get(key)
            if failure is None:
                return None
            if failure.expires_at <= time.monotonic():
                cls._failures.pop(key, None)
                return None
            return {
                "fingerprint": repr(failure.fingerprint),
                "error": failure.error,
            }

    @classmethod
    def _delete_failure(cls, key: str) -> None:
        """Remove failure state for a registry key."""
        if failure_backend.get_failure_backend_name() == "memory":
            with cls._lock:
                cls._failures.pop(key, None)
            return
        try:
            failure_backend.delete_failure(cls.__name__, key)
        except Exception:
            pass
        with cls._lock:
            cls._failures.pop(key, None)

    @classmethod
    def _clear_failures(cls) -> None:
        """Clear failure state for this registry."""
        if failure_backend.get_failure_backend_name() == "memory":
            cls._failures.clear()
            return
        try:
            failure_backend.clear_failures(cls.__name__)
        except Exception:
            pass
        with cls._lock:
            cls._failures.clear()

    @classmethod
    def _dispose_entry(cls, entry: RegistryEntry[EngineT]) -> None:
        """Dispose a registry entry's engine."""
        cls._dispose_engine(entry.engine)

    @staticmethod
    def _create_engine(config: EngineConfig) -> EngineT:
        """Create an engine for the concrete registry implementation."""
        raise NotImplementedError

    @staticmethod
    def _dispose_engine(engine: EngineT) -> None:
        """Dispose an engine for the concrete registry implementation."""
        raise NotImplementedError
