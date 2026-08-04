from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqltoolkit.connection.config import (
    EngineConfig,
    _bool_env,
    _build_env_prefix,
    _coerce_bool,
    _coerce_ini_scalar,
    _extract_engine_kwargs,
    _extract_on_connect_statements,
    _freeze_value,
    _infer_dialect_from_url,
    _int_env,
    _json_env,
    _normalize_file_config_entry,
    _read_config_file,
    _read_ini_config,
    _require_env,
    _validate_engine_config,
    build_engine_config,
    build_named_registry_key,
    build_registry_key,
    config_from_kwargs,
    load_config_from_env,
    load_config_from_file,
    normalize_access_mode,
)


@pytest.mark.unit
def test_basic_config_helpers() -> None:
    assert normalize_access_mode(" ReadOnly ") == "readonly"
    assert normalize_access_mode(" Reporting ") == "reporting"
    with pytest.raises(ValueError, match="access_mode must not be empty"):
        normalize_access_mode(" ")
    assert build_registry_key(
        dialect="postgresql",
        tenant="default",
        access_mode="readwrite",
        async_mode=False,
    ) == "postgresql:default:readwrite:sync"
    assert build_named_registry_key(
        key="main",
        access_mode="readonly",
        async_mode=True,
    ) == "registry:main:readonly:async"
    assert _build_env_prefix(
        dialect="postgresql",
        tenant="default",
        access_mode="readwrite",
    ) == "SQLTOOLKIT__POSTGRESQL__DEFAULT__READWRITE"


@pytest.mark.unit
def test_config_from_kwargs_requires_dialect_or_db_url() -> None:
    with pytest.raises(ValueError, match="Either db_url or dialect is required"):
        config_from_kwargs()


@pytest.mark.unit
def test_config_from_kwargs_infers_dialect_from_url() -> None:
    config = config_from_kwargs(
        db_url="postgresql+psycopg://user:password@localhost:5432/app",
        engine_options={"pool_recycle": 1800},
    )
    assert config.url.startswith("postgresql+psycopg://")
    assert config.engine_kwargs["pool_recycle"] == 1800


@pytest.mark.unit
def test_normalize_file_config_entry_merges_aliases() -> None:
    normalized = _normalize_file_config_entry(
        {
            "url": "sqlite+pysqlite:///:memory:",
            "options": {"echo": True},
            "session_settings": {"foreign_keys": True},
        }
    )

    assert normalized["db_url"] == "sqlite+pysqlite:///:memory:"
    assert normalized["engine_options"] == {"echo": True}
    assert normalized["session_settings"] == {"foreign_keys": True}


@pytest.mark.unit
def test_read_config_file_errors(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        _read_config_file(missing)

    txt_path = tmp_path / "config.txt"
    txt_path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported config file format"):
        _read_config_file(txt_path)

    json_path = tmp_path / "config.json"
    json_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level mapping"):
        _read_config_file(json_path)


@pytest.mark.unit
def test_load_config_from_file_errors(tmp_path: Path) -> None:
    missing_entry = tmp_path / "config.json"
    missing_entry.write_text(json.dumps({"databases": {"sqlite": {}}}), encoding="utf-8")
    with pytest.raises(KeyError, match="Missing database config"):
        load_config_from_file(
            dialect="sqlite",
            tenant="default",
            access_mode="readwrite",
            config_path=missing_entry,
        )

    invalid_entry = tmp_path / "invalid.json"
    invalid_entry.write_text(
        json.dumps({"databases": {"sqlite": {"default": {"readwrite": "bad"}}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be a mapping"):
        load_config_from_file(
            dialect="sqlite",
            tenant="default",
            access_mode="readwrite",
            config_path=invalid_entry,
        )


@pytest.mark.unit
def test_load_config_from_file_supports_custom_aliases(tmp_path: Path) -> None:
    json_path = tmp_path / "config.json"
    json_path.write_text(
        json.dumps(
            {
                "databases": {
                    "sqlite": {
                        "default": {
                            "analytics": {
                                "db_url": "sqlite+pysqlite:///:memory:",
                                "engine_options": {"echo": True},
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    ini_path = tmp_path / "config.ini"
    ini_path.write_text(
        "[databases.sqlite.default.analytics]\n"
        "db_url = sqlite+pysqlite:///:memory:\n"
        "\n"
        "[databases.sqlite.default.analytics.engine_options]\n"
        "echo = true\n",
        encoding="utf-8",
    )

    json_config = load_config_from_file(
        dialect="sqlite",
        tenant="default",
        access_mode="analytics",
        config_path=json_path,
    )
    ini_config = load_config_from_file(
        dialect="sqlite",
        tenant="default",
        access_mode="Analytics",
        config_path=ini_path,
    )

    assert json_config.url == "sqlite+pysqlite:///:memory:"
    assert json_config.engine_kwargs["echo"] is True
    assert ini_config.url == "sqlite+pysqlite:///:memory:"
    assert ini_config.engine_kwargs["echo"] is True


@pytest.mark.unit
def test_ini_reader_validation_errors() -> None:
    with pytest.raises(ValueError, match="INI sections must look like"):
        _read_ini_config("[broken.section]\na = 1\n")

    with pytest.raises(ValueError, match="Unsupported INI subsection"):
        _read_ini_config(
            "[databases.sqlite.default.readwrite.unsupported]\n"
            "a = 1\n"
        )

    with pytest.raises(ValueError, match="must decode to a JSON object"):
        _read_ini_config(
            "[databases.sqlite.default.readwrite]\n"
            "connect_args = []\n"
        )


@pytest.mark.unit
def test_ini_scalar_and_env_coercion_helpers() -> None:
    assert _coerce_ini_scalar("true") is True
    assert _coerce_ini_scalar("10") == 10
    assert _coerce_ini_scalar("1.25") == 1.25
    assert _coerce_ini_scalar("text") == "text"
    assert _coerce_ini_scalar("   ") == "   "

    env = {"A": "5", "B": "true", "C": '{"x": 1}', "REQ": "value"}
    assert _int_env(env, "A", 0) == 5
    assert _bool_env(env, "B", False) is True
    assert _json_env(env, "C", {}) == {"x": 1}
    assert _require_env(env, "REQ") == "value"
    assert _coerce_bool("off") is False
    assert _coerce_bool(1) is True

    with pytest.raises(KeyError, match="Required environment variable"):
        _require_env({}, "REQ")
    with pytest.raises(ValueError, match="must decode to an object"):
        _json_env({"BAD": "[]"}, "BAD", {})


@pytest.mark.unit
def test_load_config_from_env_errors_and_aliases() -> None:
    with pytest.raises(KeyError, match="No environment configuration found"):
        load_config_from_env(
            dialect="sqlite",
            tenant="default",
            access_mode="readwrite",
            env={},
        )

    with pytest.raises(KeyError, match="No environment configuration found"):
        load_config_from_env(
            dialect="sqlite",
            tenant="default",
            access_mode="archive",
            env={"X": "1"},
        )

    config = load_config_from_env(
        dialect="sqlite",
        tenant="",
        access_mode="readwrite",
        env={
            "SQLTOOLKIT__SQLITE__DEFAULT__READWRITE__URL": "sqlite+pysqlite:///:memory:",
            "SQLTOOLKIT__SQLITE__DEFAULT__READWRITE__OPTIONS": '{"echo": true}',
            "SQLTOOLKIT__SQLITE__DEFAULT__READWRITE__SESSION_SETTINGS": '{"foreign_keys": true}',
        },
    )
    assert config.url == "sqlite+pysqlite:///:memory:"
    assert config.engine_kwargs["echo"] is True
    assert config.on_connect_statements == ("PRAGMA foreign_keys = 1",)

    alias_config = load_config_from_env(
        dialect="sqlite",
        tenant="default",
        access_mode="Analytics",
        env={
            "SQLTOOLKIT__SQLITE__DEFAULT__ANALYTICS__URL": "sqlite+pysqlite:///:memory:",
        },
    )
    assert alias_config.url == "sqlite+pysqlite:///:memory:"


@pytest.mark.unit
def test_extract_helpers_cover_oracle_and_empty_cases() -> None:
    raw = {
        "connect_args": {"mode": "thin"},
        "dsn": "dbhost/service",
        "username": "user",
        "password": "secret",
    }
    kwargs = _extract_engine_kwargs(dialect="oracle", raw_config=raw)
    assert kwargs["connect_args"]["dsn"] == "dbhost/service"
    assert kwargs["connect_args"]["user"] == "user"
    assert kwargs["connect_args"]["password"] == "secret"

    assert _extract_on_connect_statements(dialect="sqlite", raw_config={}) == ()


@pytest.mark.unit
def test_engine_config_validation_and_infer_helpers() -> None:
    assert _infer_dialect_from_url("mysql+pymysql://u:p@localhost/db") == "mysql"

    with pytest.raises(ValueError, match="db_url is required"):
        _infer_dialect_from_url(None)

    for config, message in [
        (EngineConfig(url="sqlite://", engine_kwargs={"pool_size": -1}), "pool_size"),
        (EngineConfig(url="sqlite://", engine_kwargs={"max_overflow": -2}), "max_overflow"),
        (EngineConfig(url="sqlite://", engine_kwargs={"pool_pre_ping": "yes"}), "pool_pre_ping"),
        (EngineConfig(url="sqlite://", engine_kwargs={"echo": "yes"}), "echo"),
        (EngineConfig(url="sqlite://", engine_kwargs={"connect_args": []}), "connect_args"),
    ]:
        with pytest.raises(ValueError, match=message):
            _validate_engine_config(config)


@pytest.mark.unit
def test_build_engine_config_and_freeze_value_cover_more_shapes() -> None:
    config = build_engine_config(
        dialect="sqlite",
        async_mode=False,
        raw_config={
            "db_url": "sqlite+pysqlite:///:memory:",
            "engine_options": {"echo": False},
            "session_settings": {"foreign_keys": True},
        },
    )
    assert config.to_engine_kwargs() == {
        "url": "sqlite+pysqlite:///:memory:",
        "echo": False,
    }
    assert _freeze_value({"a": [1, 2], "b": {"x", "y"}})
