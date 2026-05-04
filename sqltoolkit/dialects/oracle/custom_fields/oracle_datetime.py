"""Oracle timezone-aware datetime custom field."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytz
from sqlalchemy.dialects.oracle import TIMESTAMP
from sqlalchemy.types import TypeDecorator


class OracleTimezoneAwareDateTime(TypeDecorator):
    """Persist timezone-aware datetimes in UTC and render results in a target timezone."""

    impl = TIMESTAMP(timezone=True)
    cache_ok = False

    def __init__(self, target_timezone: str = "UTC", return_as_iso: bool = True, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._target_timezone_name = target_timezone
        self.target_timezone = pytz.timezone(target_timezone)
        self.return_as_iso = return_as_iso

    def process_bind_param(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"Invalid datetime format: {value}") from exc

        if not isinstance(value, datetime):
            raise TypeError("Unsupported data type for datetime field.")
        if value.tzinfo is None:
            raise ValueError("Naive datetime provided; timezone information is required.")
        return value.astimezone(pytz.UTC)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("Unexpected data type from database.")
        if value.tzinfo is None:
            value = value.replace(tzinfo=pytz.UTC)
        local_time = value.astimezone(self.target_timezone)
        if self.return_as_iso:
            return local_time.isoformat()
        return local_time

    def copy(self, **kwargs: Any) -> "OracleTimezoneAwareDateTime":
        return type(self)(
            target_timezone=self._target_timezone_name,
            return_as_iso=self.return_as_iso,
            **kwargs,
        )
