"""Asynchronous SQLAlchemy engine registry."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import logging
import os
from threading import RLock
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sqltoolkit.connection._engine_base import (
    BaseEngineRegistry,
    FailureEntry,
    RegistryEntry,
    read_failure_ttl_from_env,
    read_max_entries_from_env,
)
from sqltoolkit.connection.config import (
    DEFAULT_ALIAS,
    EngineConfig,
    build_named_registry_key,
    config_from_kwargs,
    normalize_alias,
)

_logger = logging.getLogger(__name__)
_pending_disposals: set[asyncio.Task[None]] = set()


def _finish_scheduled_disposal(task: asyncio.Task[None]) -> None:
    _pending_disposals.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        _logger.error(
            "Asynchronous engine disposal failed",
            exc_info=(type(error), error, error.__traceback__),
        )


class AsyncEngineRegistry(BaseEngineRegistry[AsyncEngine]):
    """Process-local registry for asynchronous SQLAlchemy engines."""

    _entries: OrderedDict[str, RegistryEntry[AsyncEngine]] = OrderedDict()
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
    def get_engine(
        cls,
        *,
        key: str,
        db_url: str | None = None,
        dialect: str | None = None,
        driver: str | None = None,
        alias: str = DEFAULT_ALIAS,
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
        """Return a cached asynchronous engine for the given alias and config."""
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
        return cls.get_or_create(
            key=build_named_registry_key(
                key=key,
                alias=normalize_alias(alias),
                async_mode=True,
            ),
            config=config,
        )

    @staticmethod
    def _create_engine(config: EngineConfig) -> AsyncEngine:
        """Create an asynchronous SQLAlchemy engine."""
        return create_async_engine(**config.to_engine_kwargs())

    @staticmethod
    def _dispose_engine(engine: AsyncEngine) -> None:
        """Dispose an async engine, scheduling cleanup if called in an event loop."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(engine.dispose())
        else:
            task = loop.create_task(engine.dispose())
            _pending_disposals.add(task)
            task.add_done_callback(_finish_scheduled_disposal)

    @classmethod
    def dispose_all(cls) -> None:
        """Synchronously dispose async engines when no event loop is running."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(cls.adispose_all())
            return
        raise RuntimeError(
            "Cannot synchronously dispose async engines while an event loop is running; "
            "await AsyncEngineRegistry.adispose_all() instead"
        )

    @classmethod
    async def adispose_all(cls) -> None:
        """Dispose all cached async engines using SQLAlchemy's async API."""
        cls._reset_if_forked()
        with cls._lock:
            entries = list(cls._entries.values())
            cls._entries.clear()
        cls._clear_failures()

        errors: list[Exception] = []
        for entry in entries:
            try:
                await entry.engine.dispose()
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[0]

    @classmethod
    def dispose_registry_key(cls, registry_key: str) -> bool:
        """Remove an async engine and schedule its disposal if needed."""
        cls._reset_if_forked()
        with cls._lock:
            entry = cls._entries.pop(registry_key, None)
        cls._delete_failure(registry_key)
        if entry is None:
            return False
        cls._dispose_entry(entry)
        return True

    @classmethod
    async def adispose_registry_key(cls, registry_key: str) -> bool:
        """Remove and asynchronously dispose one cached async engine."""
        cls._reset_if_forked()
        with cls._lock:
            entry = cls._entries.pop(registry_key, None)
        cls._delete_failure(registry_key)
        if entry is None:
            return False
        await entry.engine.dispose()
        return True


__all__ = ["AsyncEngineRegistry"]
