"""Synchronous SQLAlchemy session registry."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class SyncSessionEntry:
    """Cached synchronous sessionmaker entry."""

    engine: Engine
    sessionmaker: sessionmaker[Session]
    options: tuple[tuple[str, Any], ...]


class SyncSessionRegistry:
    """Process-local registry for synchronous SQLAlchemy session factories."""

    _entries: dict[str, SyncSessionEntry] = {}
    _lock = RLock()

    @classmethod
    def get_sessionmaker(
        cls,
        *,
        key: str,
        engine: Engine,
        **session_options: Any,
    ) -> sessionmaker[Session]:
        """Return a cached synchronous sessionmaker for an engine."""
        options = cls._freeze_options(session_options)
        with cls._lock:
            existing = cls._entries.get(key)
            if existing is not None:
                if existing.engine is not engine or existing.options != options:
                    raise ValueError(
                        f"Session key '{key}' is already registered with different settings"
                    )
                return existing.sessionmaker

            factory = sessionmaker(bind=engine, **session_options)
            cls._entries[key] = SyncSessionEntry(
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
        engine: Engine,
        **session_options: Any,
    ) -> Session:
        """Create a Session from a cached synchronous sessionmaker."""
        return cls.get_sessionmaker(
            key=key,
            engine=engine,
            **session_options,
        )()

    @classmethod
    def dispose_registry_key(cls, registry_key: str) -> bool:
        """Remove one synchronous sessionmaker from the cache."""
        with cls._lock:
            return cls._entries.pop(registry_key, None) is not None

    @classmethod
    def dispose_all(cls) -> None:
        """Clear all cached synchronous sessionmakers."""
        with cls._lock:
            cls._entries.clear()

    @classmethod
    def list_registry_keys(cls) -> list[str]:
        """Return cache keys for synchronous sessionmakers."""
        with cls._lock:
            return sorted(cls._entries)

    @classmethod
    def get_registry_size(cls) -> int:
        """Return the number of cached synchronous sessionmakers."""
        with cls._lock:
            return len(cls._entries)

    @staticmethod
    def _freeze_options(options: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
        """Convert session options to a comparable cache fingerprint."""
        return tuple(sorted((key, repr(value)) for key, value in options.items()))


__all__ = ["SyncSessionRegistry", "SyncSessionEntry"]
