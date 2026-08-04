"""Asynchronous SQLAlchemy session registry."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@dataclass(frozen=True)
class AsyncSessionEntry:
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    options: tuple[tuple[str, Any], ...]


class AsyncSessionRegistry:
    """Process-local registry for asynchronous SQLAlchemy session factories."""

    _entries: dict[str, AsyncSessionEntry] = {}
    _lock = RLock()

    @classmethod
    def get_sessionmaker(
        cls,
        *,
        key: str,
        engine: AsyncEngine,
        **session_options: Any,
    ) -> async_sessionmaker[AsyncSession]:
        options = cls._freeze_options(session_options)
        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                if existing.engine is not engine or existing.options != options:
                    raise ValueError(
                        f"Session key '{key}' is already registered with different settings"
                    )
                return existing.sessionmaker

            factory = async_sessionmaker(bind=engine, **session_options)
            cls._entries[key] = AsyncSessionEntry(
                engine=engine,
                sessionmaker=factory,
                options=options,
            )
            return factory

    @classmethod
    def session_factory(
        cls,
        *,
        key: str,
        engine: AsyncEngine,
        **session_options: Any,
    ) -> AsyncSession:
        return cls.get_sessionmaker(
            key=key,
            engine=engine,
            **session_options,
        )()

    @classmethod
    def dispose_registry_key(cls, registry_key: str) -> bool:
        with cls._lock:
            return cls._entries.pop(registry_key, None) is not None

    @classmethod
    def dispose_all(cls) -> None:
        with cls._lock:
            cls._entries.clear()

    @classmethod
    def list_registry_keys(cls) -> list[str]:
        with cls._lock:
            return sorted(cls._entries)

    @classmethod
    def get_registry_size(cls) -> int:
        with cls._lock:
            return len(cls._entries)

    @staticmethod
    def _freeze_options(options: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
        return tuple(sorted((key, repr(value)) for key, value in options.items()))


__all__ = ["AsyncSessionRegistry", "AsyncSessionEntry"]
