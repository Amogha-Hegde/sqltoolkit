"""Oracle JSON custom field."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.dialects.oracle import CLOB
from sqlalchemy.types import TypeDecorator


class OracleJSON(TypeDecorator):
    """Store JSON-compatible payloads in Oracle CLOB columns."""

    impl = CLOB
    cache_ok = False

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        """Serialize JSON-compatible Python values for Oracle storage."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Deserialize Oracle JSON text when possible."""
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value
