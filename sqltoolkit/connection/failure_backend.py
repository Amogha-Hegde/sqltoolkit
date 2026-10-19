"""Storage backends for short-lived engine creation failure records."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

_redis_client: Any | None = None


def get_failure_backend_name() -> str:
    """Return the configured failure backend name."""
    backend = os.getenv("SQLTOOLKIT_FAILURE_BACKEND", "memory").strip().lower()
    if backend not in {"memory", "redis"}:
        raise ValueError("SQLTOOLKIT_FAILURE_BACKEND must be 'memory' or 'redis'")
    return backend


def _redis() -> Any:
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("SQLTOOLKIT_REDIS_URL")
        if not redis_url:
            raise ValueError("SQLTOOLKIT_REDIS_URL is required for the Redis failure backend")
        try:
            from redis import Redis
        except ImportError as exc:
            raise ImportError(
                "Redis failure storage requires the optional dependency; "
                "install sqltoolkit[redis]"
            ) from exc
        _redis_client = Redis.from_url(redis_url, decode_responses=True)
    return _redis_client


def _redis_key(registry: str, key: str) -> str:
    namespace = os.getenv("SQLTOOLKIT_REDIS_FAILURE_PREFIX", "sqltoolkit:failures").strip(":")
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"{namespace}:{registry}:{digest}"


def read_failure(registry: str, key: str) -> dict[str, Any] | None:
    """Read a JSON-serializable failure record from Redis."""
    value = _redis().get(_redis_key(registry, key))
    return json.loads(value) if value else None


def write_failure(registry: str, key: str, record: dict[str, Any], ttl: float) -> None:
    """Write a failure record with a Redis expiration."""
    _redis().set(_redis_key(registry, key), json.dumps(record), ex=max(1, int(ttl)))


def delete_failure(registry: str, key: str) -> None:
    """Delete one Redis failure record."""
    _redis().delete(_redis_key(registry, key))


def clear_failures(registry: str) -> None:
    """Delete failure records for one engine registry."""
    namespace = os.getenv("SQLTOOLKIT_REDIS_FAILURE_PREFIX", "sqltoolkit:failures").strip(":")
    pattern = f"{namespace}:{registry}:*"
    client = _redis()
    keys = list(client.scan_iter(match=pattern, count=500))
    if keys:
        client.delete(*keys)


__all__ = [
    "clear_failures",
    "delete_failure",
    "get_failure_backend_name",
    "read_failure",
    "write_failure",
]
