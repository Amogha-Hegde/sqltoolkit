"""Asynchronous SQLAlchemy engine registry."""

from __future__ import annotations

from collections import OrderedDict
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
    DEFAULT_ACCESS_MODE,
    EngineConfig,
    build_named_registry_key,
    config_from_kwargs,
    normalize_access_mode,
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
                access_mode=normalize_access_mode(access_mode),
                async_mode=True,
            ),
            config=config,
        )

    @staticmethod
    def _create_engine(config: EngineConfig) -> AsyncEngine:
        return create_async_engine(**config.to_engine_kwargs())

    @staticmethod
    def _dispose_engine(engine: AsyncEngine) -> None:
        # AsyncEngine.dispose() is awaitable; the sync_engine path gives
        # deterministic cleanup from synchronous registry operations.
        engine.sync_engine.dispose()


__all__ = ["AsyncEngineRegistry"]
