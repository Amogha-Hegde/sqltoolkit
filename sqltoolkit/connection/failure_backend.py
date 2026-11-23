"""Configuration for database connection failure backoff."""

from __future__ import annotations

import os


def get_failure_backend_name() -> str:
    """Return the configured failure storage mode."""
    backend = os.getenv("SQLTOOLKIT_FAILURE_BACKEND", "memory").strip().lower()
    if backend not in {"memory", "none"}:
        raise ValueError("SQLTOOLKIT_FAILURE_BACKEND must be 'memory' or 'none'")
    return backend


__all__ = ["get_failure_backend_name"]
