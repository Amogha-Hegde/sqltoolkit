from __future__ import annotations

from datetime import datetime

import pytest
import pytz
from sqlalchemy import column, select

from sqltoolkit.dialects import (
    get_custom_type,
    get_custom_type_class,
    get_dialect_function,
    get_dialect_function_factory,
    get_dialect_functions,
    list_custom_types,
    list_functions,
)
from sqltoolkit.dialects.oracle.custom_fields import (
    OracleBoolean,
    OracleJSON,
    OracleTimezoneAwareDateTime,
)
from sqltoolkit.dialects.oracle.functions import oracle_paginate
from sqltoolkit.dialects.registry import get_extensions


@pytest.mark.unit
def test_oracle_boolean_round_trip_helpers() -> None:
    oracle_bool = OracleBoolean()

    assert oracle_bool.process_bind_param(True, None) == 1
    assert oracle_bool.process_bind_param(False, None) == 0
    assert oracle_bool.process_result_value(1, None) is True
    assert oracle_bool.process_result_value(0, None) is False
    assert oracle_bool.python_type is bool

    with pytest.raises(ValueError, match="only accepts bool"):
        oracle_bool.process_bind_param("yes", None)

    with pytest.raises(ValueError, match="Invalid boolean"):
        oracle_bool.process_result_value(2, None)


@pytest.mark.unit
def test_oracle_json_handles_strings_and_python_structures() -> None:
    oracle_json = OracleJSON()

    assert oracle_json.process_bind_param({"a": 1}, None) == '{"a": 1}'
    assert oracle_json.process_result_value('{"a": 1}', None) == {"a": 1}
    assert oracle_json.process_result_value({"a": 1}, None) == {"a": 1}
    assert oracle_json.process_result_value("not-json", None) == "not-json"


@pytest.mark.unit
def test_oracle_timezone_aware_datetime_validates_and_converts() -> None:
    oracle_dt = OracleTimezoneAwareDateTime(target_timezone="Asia/Kolkata", return_as_iso=False)
    source = pytz.timezone("UTC").localize(datetime(2024, 1, 1, 0, 0, 0))

    bound = oracle_dt.process_bind_param(source, None)
    result = oracle_dt.process_result_value(bound, None)
    copied = oracle_dt.copy()

    assert bound.tzinfo is not None
    assert result.tzinfo is not None
    assert copied._target_timezone_name == "Asia/Kolkata"
    assert copied.return_as_iso is False

    with pytest.raises(ValueError, match="Invalid datetime format"):
        oracle_dt.process_bind_param("not-a-datetime", None)

    with pytest.raises(ValueError, match="Naive datetime provided"):
        oracle_dt.process_bind_param(datetime(2024, 1, 1, 0, 0, 0), None)

    with pytest.raises(TypeError, match="Unsupported data type"):
        oracle_dt.process_bind_param(123, None)

    with pytest.raises(TypeError, match="Unexpected data type"):
        oracle_dt.process_result_value("wrong-type", None)


@pytest.mark.unit
def test_oracle_registry_exports_types_and_functions() -> None:
    custom_type = get_custom_type("oracle", "json")
    custom_type_cls = get_custom_type_class("oracle", "boolean")
    func_factory = get_dialect_function_factory("oracle", "sysdate")
    func_namespace = get_dialect_functions("oracle")
    expr = get_dialect_function("oracle", "nvl", column("payload"), "{}")

    assert isinstance(custom_type, OracleJSON)
    assert custom_type_cls is OracleBoolean
    assert str(func_factory()) == "sysdate"
    assert str(func_namespace.systimestamp()) == "systimestamp()"
    assert "json" in list_custom_types("oracle")
    assert "sysdate" in list_functions("oracle")
    assert str(expr) == "nvl(payload, :nvl_1)"
    assert "json" in get_extensions("oracle").custom_types

    with pytest.raises(KeyError, match="Custom type 'missing'"):
        get_custom_type_class("oracle", "missing")

    with pytest.raises(KeyError, match="Function 'missing'"):
        get_dialect_function_factory("oracle", "missing")


@pytest.mark.unit
def test_oracle_paginate_applies_limit_and_offset() -> None:
    statement = select(column("id"))
    paginated = oracle_paginate(statement, limit=10, offset=5)
    compiled = str(paginated)

    assert "LIMIT" in compiled
    assert "OFFSET" in compiled


@pytest.mark.unit
def test_invalid_dialect_registry_access_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported dialect"):
        get_extensions("db2")
