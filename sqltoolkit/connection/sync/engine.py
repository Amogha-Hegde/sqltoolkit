"""Synchronous SQLAlchemy engine registry."""

from __future__ import annotations

from collections import OrderedDict
import os
from threading import RLock
from typing import Any, Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

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


class SyncEngineRegistry(BaseEngineRegistry[Engine]):
    """Process-local registry for synchronous SQLAlchemy engines."""

    _entries: OrderedDict[str, RegistryEntry[Engine]] = OrderedDict()
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
    ) -> Engine:
        """Return a cached synchronous engine for the given alias and config."""
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
        return cls.get_or_create(
            key=build_named_registry_key(
                key=key,
                access_mode=normalize_access_mode(access_mode),
                async_mode=False,
            ),
            config=config,
        )

    @staticmethod
    def _create_engine(config: EngineConfig) -> Engine:
        """Create a synchronous SQLAlchemy engine."""
        return create_engine(**config.to_engine_kwargs())

    @staticmethod
    def _dispose_engine(engine: Engine) -> None:
        """Dispose a synchronous SQLAlchemy engine."""
        engine.dispose()


__all__ = ["SyncEngineRegistry"]
