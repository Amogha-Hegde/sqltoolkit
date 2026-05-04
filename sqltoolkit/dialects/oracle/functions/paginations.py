"""Oracle pagination helpers."""

from __future__ import annotations

from sqlalchemy.sql import Select


def oracle_paginate(statement: Select, *, limit: int, offset: int = 0) -> Select:
    """Apply Oracle-compatible OFFSET/FETCH pagination to a select statement."""

    return statement.offset(offset).limit(limit)
