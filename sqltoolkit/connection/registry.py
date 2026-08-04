"""Public engine and session registry facade."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Mapping, cast

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from ._engine_base import (
    FailureEntry,
    RegistryEntry,
    read_failure_ttl_from_env,
    read_max_entries_from_env,
)
from .config import (
    DEFAULT_ACCESS_MODE,
    EngineConfig,
    build_named_registry_key,
    build_registry_key,
    load_config_from_env,
    load_config_from_file,
    normalize_access_mode,
)
from .sync.engine import SyncEngineRegistry
from .sync.session import SyncSessionRegistry
from sqltoolkit.dialects import normalize_dialect

_async_engine_module = import_module("sqltoolkit.connection.async.engine")
_async_session_module = import_module("sqltoolkit.connection.async.session")
AsyncEngineRegistry = _async_engine_module.AsyncEngineRegistry
AsyncSessionRegistry = _async_session_module.AsyncSessionRegistry


def _read_max_entries_from_env() -> int:
    """Read the configured maximum registry size."""
    return read_max_entries_from_env()


def _read_failure_ttl_from_env() -> float:
    """Read the configured engine creation failure backoff TTL."""
    return read_failure_ttl_from_env()


class EngineRegistry:
    """Compatibility facade over separate sync and async registries."""

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
        """Return a cached synchronous engine for direct keyword config."""
        return SyncEngineRegistry.get_engine(
            key=key,
            db_url=db_url,
            dialect=dialect,
            driver=driver,
            access_mode=access_mode,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
            connect_args=connect_args,
            query=query,
            engine_options=engine_options,
            session_settings=session_settings,
            **dialect_options,
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
        """Return a cached asynchronous engine for direct keyword config."""
        return AsyncEngineRegistry.get_engine(
            key=key,
            db_url=db_url,
            dialect=dialect,
            driver=driver,
            access_mode=access_mode,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            echo=echo,
            connect_args=connect_args,
            query=query,
            engine_options=engine_options,
            session_settings=session_settings,
            **dialect_options,
        )

    @classmethod
    def get_sessionmaker(
        cls,
        *,
        key: str,
        engine: Engine,
        access_mode: str = DEFAULT_ACCESS_MODE,
        **session_options: Any,
    ) -> sessionmaker[Session]:
        """Return a cached synchronous SQLAlchemy sessionmaker."""
        return SyncSessionRegistry.get_sessionmaker(
            key=build_named_registry_key(
                key=key,
                access_mode=normalize_access_mode(access_mode),
                async_mode=False,
            ),
            engine=engine,
            **session_options,
        )

    @classmethod
    def get_async_sessionmaker(
        cls,
        *,
        key: str,
        engine: AsyncEngine,
        access_mode: str = DEFAULT_ACCESS_MODE,
        **session_options: Any,
    ) -> async_sessionmaker[AsyncSession]:
        """Return a cached asynchronous SQLAlchemy sessionmaker."""
        return AsyncSessionRegistry.get_sessionmaker(
            key=build_named_registry_key(
                key=key,
                access_mode=normalize_access_mode(access_mode),
                async_mode=True,
            ),
            engine=engine,
            **session_options,
        )

    @classmethod
    def session_factory(
        cls,
        *,
        key: str,
        engine: Engine,
        access_mode: str = DEFAULT_ACCESS_MODE,
        **session_options: Any,
    ) -> Session:
        """Create a synchronous Session from a cached sessionmaker."""
        return cls.get_sessionmaker(
            key=key,
            engine=engine,
            access_mode=access_mode,
            **session_options,
        )()

    @classmethod
    def async_session_factory(
        cls,
        *,
        key: str,
        engine: AsyncEngine,
        access_mode: str = DEFAULT_ACCESS_MODE,
        **session_options: Any,
    ) -> AsyncSession:
        """Create an AsyncSession from a cached async sessionmaker."""
        return cls.get_async_sessionmaker(
            key=key,
            engine=engine,
            access_mode=access_mode,
            **session_options,
        )()

    @classmethod
    def dispose_all(cls) -> None:
        """Dispose every cached engine and sessionmaker."""
        SyncSessionRegistry.dispose_all()
        AsyncSessionRegistry.dispose_all()
        SyncEngineRegistry.dispose_all()
        AsyncEngineRegistry.dispose_all()

    @classmethod
    def dispose_engine(
        cls,
        *,
        key: str,
        access_mode: str = DEFAULT_ACCESS_MODE,
        async_mode: bool = False,
    ) -> bool:
        """Dispose one cached engine and its matching sessionmaker by key."""
        registry_key = build_named_registry_key(
            key=key,
            access_mode=normalize_access_mode(access_mode),
            async_mode=async_mode,
        )
        return cls.dispose_registry_key(registry_key)

    @classmethod
    def dispose_registry_key(cls, registry_key: str) -> bool:
        """Dispose one cache entry by its full registry key."""
        removed_session = (
            SyncSessionRegistry.dispose_registry_key(registry_key)
            or AsyncSessionRegistry.dispose_registry_key(registry_key)
        )
        removed_engine = (
            SyncEngineRegistry.dispose_registry_key(registry_key)
            or AsyncEngineRegistry.dispose_registry_key(registry_key)
        )
        return removed_session or removed_engine

    @classmethod
    def list_registry_keys(cls) -> list[str]:
        """Return full registry keys for all cached engines."""
        return sorted(
            [
                *SyncEngineRegistry.list_registry_keys(),
                *AsyncEngineRegistry.list_registry_keys(),
            ]
        )

    @classmethod
    def list_engines(cls) -> list[str]:
        """Return full registry keys for all cached engines."""
        return cls.list_registry_keys()

    @classmethod
    def list_session_registry_keys(cls) -> list[str]:
        """Return full registry keys for all cached sessionmakers."""
        return sorted(
            [
                *SyncSessionRegistry.list_registry_keys(),
                *AsyncSessionRegistry.list_registry_keys(),
            ]
        )

    @classmethod
    def get_registry_size(cls) -> int:
        """Return the total number of cached sync and async engines."""
        return (
            SyncEngineRegistry.get_registry_size()
            + AsyncEngineRegistry.get_registry_size()
        )

    @classmethod
    def get_session_registry_size(cls) -> int:
        """Return the total number of cached sync and async sessionmakers."""
        return (
            SyncSessionRegistry.get_registry_size()
            + AsyncSessionRegistry.get_registry_size()
        )

    @classmethod
    def get_registry_stats(cls) -> dict[str, int]:
        """Return aggregate sync and async engine registry counters."""
        sync_stats = SyncEngineRegistry.get_registry_stats()
        async_stats = AsyncEngineRegistry.get_registry_stats()
        return {
            "hits": sync_stats["hits"] + async_stats["hits"],
            "misses": sync_stats["misses"] + async_stats["misses"],
            "evictions": sync_stats["evictions"] + async_stats["evictions"],
            "failure_backoffs": (
                sync_stats["failure_backoffs"] + async_stats["failure_backoffs"]
            ),
            "creations": sync_stats["creations"] + async_stats["creations"],
            "size": sync_stats["size"] + async_stats["size"],
            "max_entries": sync_stats["max_entries"],
            "total_max_entries": sync_stats["max_entries"] + async_stats["max_entries"],
            "sync_size": sync_stats["size"],
            "async_size": async_stats["size"],
            "sync_max_entries": sync_stats["max_entries"],
            "async_max_entries": async_stats["max_entries"],
        }

    @classmethod
    def get_engine_config(cls, registry_key: str) -> EngineConfig | None:
        """Return the normalized config for a cached engine, if present."""
        return (
            SyncEngineRegistry.get_engine_config(registry_key)
            or AsyncEngineRegistry.get_engine_config(registry_key)
        )

    @classmethod
    def set_max_entries(cls, max_entries: int) -> None:
        """Set the maximum entry count on both sync and async registries."""
        SyncEngineRegistry.set_max_entries(max_entries)
        AsyncEngineRegistry.set_max_entries(max_entries)

    @staticmethod
    def _configure_engine(engine: Engine | AsyncEngine, config: EngineConfig) -> None:
        """Attach per-connection setup hooks to an engine."""
        SyncEngineRegistry._configure_engine(engine, config)

    @staticmethod
    def _dispose_entry(entry: RegistryEntry[Any]) -> None:
        """Dispose a sync or async registry entry."""
        engine = entry.engine
        if isinstance(engine, AsyncEngine):
            AsyncEngineRegistry._dispose_engine(engine)
            return
        SyncEngineRegistry._dispose_engine(cast(Engine, engine))

    @staticmethod
    def _is_async_entry(entry: RegistryEntry[Any]) -> bool:
        """Return whether a registry entry contains an AsyncEngine."""
        return isinstance(entry.engine, AsyncEngine)

    @classmethod
    def _reset_if_forked(cls) -> None:
        """Clear child-process registries after a fork."""
        SyncEngineRegistry._reset_if_forked()
        AsyncEngineRegistry._reset_if_forked()

    @classmethod
    def _get_or_create_sync_engine(
        cls,
        *,
        key: str,
        config: EngineConfig,
    ) -> Engine:
        """Return a sync engine from the sync registry."""
        return SyncEngineRegistry.get_or_create(key=key, config=config)

    @classmethod
    def _get_or_create_async_engine(
        cls,
        *,
        key: str,
        config: EngineConfig,
    ) -> AsyncEngine:
        """Return an async engine from the async registry."""
        return AsyncEngineRegistry.get_or_create(key=key, config=config)


def _get_env_engine(
    *,
    dialect: str,
    tenant: str,
    access_mode: str,
    async_mode: bool,
    env: Mapping[str, str] | None,
) -> Engine | AsyncEngine:
    """Create or retrieve an engine from environment configuration."""
    dialect_name = normalize_dialect(dialect)
    alias = normalize_access_mode(access_mode)
    tenant_name = tenant.strip() or "default"
    config = load_config_from_env(
        dialect=dialect_name,
        tenant=tenant_name,
        access_mode=alias,
        async_mode=async_mode,
        env=env,
    )
    registry_key = build_registry_key(
        dialect=dialect_name,
        tenant=tenant_name,
        access_mode=alias,
        async_mode=async_mode,
    )
    if async_mode:
        return AsyncEngineRegistry.get_or_create(key=registry_key, config=config)
    return SyncEngineRegistry.get_or_create(key=registry_key, config=config)


def _get_file_engine(
    *,
    dialect: str,
    tenant: str,
    config_path: str,
    access_mode: str,
    async_mode: bool,
) -> Engine | AsyncEngine:
    """Create or retrieve an engine from file configuration."""
    dialect_name = normalize_dialect(dialect)
    alias = normalize_access_mode(access_mode)
    tenant_name = tenant.strip() or "default"
    config = load_config_from_file(
        dialect=dialect_name,
        tenant=tenant_name,
        access_mode=alias,
        async_mode=async_mode,
        config_path=config_path,
    )
    registry_key = build_registry_key(
        dialect=dialect_name,
        tenant=tenant_name,
        access_mode=alias,
        async_mode=async_mode,
    )
    if async_mode:
        return AsyncEngineRegistry.get_or_create(key=registry_key, config=config)
    return SyncEngineRegistry.get_or_create(key=registry_key, config=config)


def get_engine(
    *,
    dialect: str,
    tenant: str = "default",
    access_mode: str = DEFAULT_ACCESS_MODE,
    env: Mapping[str, str] | None = None,
) -> Engine:
    """Return a synchronous engine configured from environment variables."""
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
    """Return an asynchronous engine configured from environment variables."""
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
    """Return a synchronous engine configured from a JSON or INI file."""
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
    """Return an asynchronous engine configured from a JSON or INI file."""
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


__all__ = [
    "AsyncEngineRegistry",
    "AsyncSessionRegistry",
    "EngineRegistry",
    "FailureEntry",
    "RegistryEntry",
    "SyncEngineRegistry",
    "SyncSessionRegistry",
    "get_async_engine",
    "get_async_engine_from_file",
    "get_engine",
    "get_engine_from_file",
]
