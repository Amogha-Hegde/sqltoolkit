"""Configuration loading and normalization helpers."""

from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from sqltoolkit.dialects import (
    build_engine_url,
    build_oracle_connect_args,
    build_session_statements,
    normalize_dialect,
)

DEFAULT_ALIAS = "default"

ENV_PREFIX = "SQLTOOLKIT"


@dataclass(frozen=True)
class EngineConfig:
    """Normalized SQLAlchemy engine configuration."""

    url: str
    engine_kwargs: dict[str, Any] = field(default_factory=dict)
    on_connect_statements: tuple[str, ...] = field(default_factory=tuple)

    def to_engine_kwargs(self) -> dict[str, Any]:
        """Return keyword arguments accepted by SQLAlchemy engine factories."""
        return {"url": self.url, **self.engine_kwargs}

    def fingerprint(self) -> tuple[Any, ...]:
        """Return a hashable representation used to compare cached engines."""
        return (
            self.url,
            _freeze_value(self.engine_kwargs),
            self.on_connect_statements,
        )


def normalize_alias(alias: str) -> str:
    """Normalize a database alias for env/file lookup and registry keys."""
    normalized = str(alias).strip().lower()
    if not normalized:
        raise ValueError("alias must not be empty")
    return normalized


def build_registry_key(
    *,
    dialect: str,
    alias: str,
    async_mode: bool,
) -> str:
    """Build the canonical cache key for dialect, alias, and interface."""
    interface = "async" if async_mode else "sync"
    return f"{dialect}:{alias}:{interface}"


def load_config_from_env(
    *,
    dialect: str,
    alias: str,
    async_mode: bool = False,
    env: Mapping[str, str] | None = None,
) -> EngineConfig:
    """Load an engine configuration from SQLTOOLKIT environment variables."""
    source = os.environ if env is None else env
    dialect = normalize_dialect(dialect)
    alias = normalize_alias(alias)
    prefix = _build_env_prefix(dialect=dialect, alias=alias)
    raw_config = _load_env_mapping(source, prefix)
    if not raw_config:
        raise KeyError(f"No environment configuration found for prefix '{prefix}'")
    return build_engine_config(dialect=dialect, async_mode=async_mode, raw_config=raw_config)


def load_config_from_file(
    *,
    dialect: str,
    alias: str,
    async_mode: bool = False,
    config_path: str | os.PathLike[str],
) -> EngineConfig:
    """Load an engine configuration from a JSON or INI config file."""
    dialect = normalize_dialect(dialect)
    alias = normalize_alias(alias)

    config_data = _read_config_file(config_path)
    try:
        alias_config = config_data["databases"][dialect][alias]
    except KeyError as exc:
        raise KeyError(
            "Missing database config for "
            f"dialect='{dialect}', alias='{alias}'"
        ) from exc

    if not isinstance(alias_config, dict):
        raise ValueError("Database config entry must be a mapping")

    return build_engine_config(
        dialect=dialect,
        async_mode=async_mode,
        raw_config=_normalize_file_config_entry(alias_config),
    )


def config_from_kwargs(
    *,
    dialect: str | None = None,
    db_url: str | None = None,
    driver: str | None = None,
    pool_size: int = 5,
    max_overflow: int = 10,
    pool_pre_ping: bool = True,
    echo: bool = False,
    connect_args: Mapping[str, Any] | None = None,
    query: Mapping[str, Any] | None = None,
    engine_options: Mapping[str, Any] | None = None,
    session_settings: Mapping[str, Any] | None = None,
    async_mode: bool = False,
    **dialect_options: Any,
) -> EngineConfig:
    """Create an engine configuration from direct keyword arguments."""
    if not db_url and not dialect:
        raise ValueError("Either db_url or dialect is required")

    raw_config: dict[str, Any] = {
        "db_url": db_url,
        "driver": driver,
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_pre_ping": pool_pre_ping,
        "echo": echo,
        "connect_args": dict(connect_args or {}),
        "query": dict(query or {}),
        "engine_options": dict(engine_options or {}),
        "session_settings": dict(session_settings or {}),
    }
    raw_config.update(dialect_options)

    target_dialect = normalize_dialect(dialect) if dialect else _infer_dialect_from_url(db_url)
    return build_engine_config(
        dialect=target_dialect,
        async_mode=async_mode,
        raw_config=raw_config,
    )


def build_engine_config(
    *,
    dialect: str,
    async_mode: bool,
    raw_config: Mapping[str, Any],
) -> EngineConfig:
    """Normalize raw config data into a validated EngineConfig."""
    data = dict(raw_config)
    on_connect_statements = _extract_on_connect_statements(
        dialect=dialect,
        raw_config=data,
    )
    engine_kwargs = _extract_engine_kwargs(dialect=dialect, raw_config=data)
    url = build_engine_url(dialect=dialect, async_mode=async_mode, config=data)
    config = EngineConfig(
        url=url,
        engine_kwargs=engine_kwargs,
        on_connect_statements=on_connect_statements,
    )
    _validate_engine_config(config)
    return config


def _normalize_file_config_entry(raw_config: Mapping[str, Any]) -> dict[str, Any]:
    """Apply file-config aliases before building an engine configuration."""
    data = dict(raw_config)

    if "url" in data and "db_url" not in data:
        data["db_url"] = data.pop("url")

    engine_options = dict(data.pop("engine_options", {}) or {})
    session_settings = dict(data.pop("session_settings", {}) or {})
    options = dict(data.pop("options", {}) or {})
    if options:
        engine_options.update(options)
    if engine_options:
        data["engine_options"] = engine_options
    if session_settings:
        data["session_settings"] = session_settings

    return data


def _build_env_prefix(*, dialect: str, alias: str) -> str:
    """Build the environment variable prefix for one database alias."""
    return "__".join(
        [
            ENV_PREFIX,
            dialect.upper(),
            alias.upper(),
        ]
    )


def _read_config_file(config_path: str | os.PathLike[str]) -> dict[str, Any]:
    """Read a JSON or INI config file into the shared nested mapping shape."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(raw)
    elif suffix == ".ini":
        data = _read_ini_config(raw)
    else:
        raise ValueError("Unsupported config file format. Use .json or .ini")

    if not isinstance(data, dict):
        raise ValueError("Config file must contain a top-level mapping")
    return data


def _read_ini_config(raw: str) -> dict[str, Any]:
    """Parse INI config sections into the same nested shape as JSON config."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(raw)

    data: dict[str, Any] = {}
    for section_name in parser.sections():
        section_path = section_name.split(".")
        if len(section_path) in {2, 3} and section_path[0] != "databases":
            section_path = ["databases", *section_path]
        if len(section_path) not in {3, 4} or section_path[0] != "databases":
            raise ValueError(
                "INI sections must look like "
                "'[databases.<dialect>.<alias>]', "
                "'[<dialect>.<alias>]', "
                "or those paths with a trailing '.database_options', '.options', '.query', or '.connect_args'"
                " or '.session_settings'"
            )

        current = data
        for part in section_path[:3]:
            current = current.setdefault(part, {})

        if len(section_path) == 3:
            section_data = _coerce_ini_section(dict(parser.items(section_name)))
            current.update(section_data)
            continue

        subsection = section_path[3].lower()
        mapped_key = {
            "database_options": "database_options",
            "query": "query",
            "options": "engine_options",
            "engine_options": "engine_options",
            "connect_args": "connect_args",
            "session_settings": "session_settings",
        }.get(subsection)
        if mapped_key is None:
            raise ValueError(
                f"Unsupported INI subsection '{subsection}'. "
                "Use database_options, options, engine_options, query, connect_args, or session_settings."
            )

        existing = dict(current.get(mapped_key, {}) or {})
        existing.update(_coerce_ini_mapping(dict(parser.items(section_name))))
        current[mapped_key] = existing

    return data


def _coerce_ini_section(section_data: Mapping[str, str]) -> dict[str, Any]:
    """Coerce scalar values from a top-level INI database section."""
    result: dict[str, Any] = {}
    int_keys = {"port", "pool_size", "max_overflow"}
    bool_keys = {"pool_pre_ping", "echo", "in_memory"}
    json_keys = {
        "connect_args",
        "query",
        "engine_options",
        "database_options",
        "options",
        "session_settings",
    }

    for key, value in section_data.items():
        if key in int_keys:
            result[key] = int(value)
        elif key in bool_keys:
            result[key] = _coerce_bool(value)
        elif key in json_keys:
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError(f"INI field '{key}' must decode to a JSON object")
            result[key] = parsed
        else:
            result[key] = value

    return result


def _coerce_ini_mapping(section_data: Mapping[str, str]) -> dict[str, Any]:
    """Coerce scalar values from a nested INI subsection."""
    return {key: _coerce_ini_scalar(value) for key, value in section_data.items()}


def _coerce_ini_scalar(value: str) -> Any:
    """Convert an INI scalar to bool, number, JSON value, or raw text."""
    stripped = value.strip()
    if not stripped:
        return value
    lowered = stripped.lower()
    if lowered in {"true", "false", "yes", "no", "on", "off", "0", "1"}:
        return _coerce_bool(stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _require_env(env: Mapping[str, str], name: str) -> str:
    """Return a required environment variable or raise KeyError."""
    value = env.get(name)
    if value in (None, ""):
        raise KeyError(f"Required environment variable '{name}' is not set")
    return value


def _int_env(env: Mapping[str, str], name: str, default: int) -> int:
    """Read an integer environment variable with a default."""
    value = env.get(name)
    return default if value in (None, "") else int(value)


def _bool_env(env: Mapping[str, str], name: str, default: bool) -> bool:
    """Read a boolean environment variable with a default."""
    value = env.get(name)
    if value in (None, ""):
        return default
    return _coerce_bool(value)


def _json_env(env: Mapping[str, str], name: str, default: dict[str, Any]) -> dict[str, Any]:
    """Read a JSON-object environment variable with a default."""
    value = env.get(name)
    if value in (None, ""):
        return default
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"Environment variable '{name}' must decode to an object")
    return parsed


def _coerce_bool(value: Any) -> bool:
    """Coerce common string and scalar representations to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _load_env_mapping(env: Mapping[str, str], prefix: str) -> dict[str, Any]:
    """Collect supported SQLTOOLKIT variables for one prefix into raw config."""
    data: dict[str, Any] = {}

    db_url = env.get(f"{prefix}__DB_URL") or env.get(f"{prefix}__URL")
    if db_url:
        data["db_url"] = db_url

    driver = env.get(f"{prefix}__DRIVER")
    if driver:
        data["driver"] = driver

    username = env.get(f"{prefix}__USERNAME") or env.get(f"{prefix}__USER")
    if username:
        data["username"] = username

    password = env.get(f"{prefix}__PASSWORD")
    if password:
        data["password"] = password

    host = env.get(f"{prefix}__HOST")
    if host:
        data["host"] = host

    port = env.get(f"{prefix}__PORT")
    if port:
        data["port"] = int(port)

    database = env.get(f"{prefix}__DATABASE") or env.get(f"{prefix}__DBNAME")
    if database:
        data["database"] = database

    file_path = env.get(f"{prefix}__FILE_PATH")
    if file_path:
        data["file_path"] = file_path

    service_name = env.get(f"{prefix}__SERVICE_NAME")
    if service_name:
        data["service_name"] = service_name

    sid = env.get(f"{prefix}__SID")
    if sid:
        data["sid"] = sid

    dsn = env.get(f"{prefix}__DSN")
    if dsn:
        data["dsn"] = dsn

    dsn_name = env.get(f"{prefix}__DSN_NAME")
    if dsn_name:
        data["dsn_name"] = dsn_name

    odbc_connect = env.get(f"{prefix}__ODBC_CONNECT")
    if odbc_connect:
        data["odbc_connect"] = odbc_connect

    odbc_driver = env.get(f"{prefix}__ODBC_DRIVER")
    if odbc_driver:
        data["odbc_driver"] = odbc_driver

    charset = env.get(f"{prefix}__CHARSET")
    if charset:
        data["charset"] = charset

    if f"{prefix}__IN_MEMORY" in env:
        data["in_memory"] = _bool_env(env, f"{prefix}__IN_MEMORY", False)

    if f"{prefix}__POOL_SIZE" in env:
        data["pool_size"] = _int_env(env, f"{prefix}__POOL_SIZE", 5)
    if f"{prefix}__MAX_OVERFLOW" in env:
        data["max_overflow"] = _int_env(env, f"{prefix}__MAX_OVERFLOW", 10)
    if f"{prefix}__POOL_PRE_PING" in env:
        data["pool_pre_ping"] = _bool_env(env, f"{prefix}__POOL_PRE_PING", True)
    if f"{prefix}__ECHO" in env:
        data["echo"] = _bool_env(env, f"{prefix}__ECHO", False)

    connect_args = _json_env(env, f"{prefix}__CONNECT_ARGS", {})
    if connect_args:
        data["connect_args"] = connect_args

    query = _json_env(env, f"{prefix}__QUERY", {})
    if query:
        data["query"] = query

    database_options = _json_env(env, f"{prefix}__DATABASE_OPTIONS", {})
    if database_options:
        data["database_options"] = database_options

    engine_options = _json_env(env, f"{prefix}__ENGINE_OPTIONS", {})
    options = _json_env(env, f"{prefix}__OPTIONS", {})
    if options:
        engine_options.update(options)
    if engine_options:
        data["engine_options"] = engine_options

    session_settings = _json_env(env, f"{prefix}__SESSION_SETTINGS", {})
    if session_settings:
        data["session_settings"] = session_settings

    return data


def _extract_engine_kwargs(
    *,
    dialect: str,
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    """Extract SQLAlchemy engine keyword arguments from raw config."""
    engine_options = dict(raw_config.pop("engine_options", {}) or {})

    pool_option_keys = ("echo",) if dialect == "sqlite" else (
        "pool_size",
        "max_overflow",
        "pool_pre_ping",
        "echo",
    )
    for key in pool_option_keys:
        if key in raw_config:
            engine_options[key] = raw_config.pop(key)

    connect_args = dict(raw_config.pop("connect_args", {}) or {})
    if dialect == "oracle":
        connect_args = build_oracle_connect_args(raw_config)
    if connect_args:
        engine_options["connect_args"] = connect_args

    return engine_options


def _extract_on_connect_statements(
    *,
    dialect: str,
    raw_config: dict[str, Any],
) -> tuple[str, ...]:
    """Extract per-connection session setup statements from raw config."""
    session_settings = dict(raw_config.pop("session_settings", {}) or {})
    if not session_settings:
        return ()
    return tuple(build_session_statements(dialect=dialect, settings=session_settings))


def _infer_dialect_from_url(db_url: str | None) -> str:
    """Infer the SQLAlchemy dialect name from a database URL."""
    if not db_url:
        raise ValueError("db_url is required to infer dialect")
    scheme = db_url.split("://", 1)[0]
    dialect = scheme.split("+", 1)[0]
    return normalize_dialect(dialect)


def build_named_registry_key(
    *,
    key: str,
    alias: str,
    async_mode: bool,
) -> str:
    """Build a registry key for direct EngineRegistry entries."""
    return build_registry_key(
        dialect="registry",
        alias=f"{key}:{alias}",
        async_mode=async_mode,
    )


def _validate_engine_config(config: EngineConfig) -> None:
    """Validate normalized engine options before creating an engine."""
    pool_size = config.engine_kwargs.get("pool_size")
    if pool_size is not None and int(pool_size) < 0:
        raise ValueError("pool_size must be >= 0")

    max_overflow = config.engine_kwargs.get("max_overflow")
    if max_overflow is not None and int(max_overflow) < -1:
        raise ValueError("max_overflow must be >= -1")

    pool_pre_ping = config.engine_kwargs.get("pool_pre_ping")
    if pool_pre_ping is not None and not isinstance(pool_pre_ping, bool):
        raise ValueError("pool_pre_ping must be a bool")

    echo = config.engine_kwargs.get("echo")
    if echo is not None and not isinstance(echo, bool):
        raise ValueError("echo must be a bool")

    connect_args = config.engine_kwargs.get("connect_args")
    if connect_args is not None and not isinstance(connect_args, dict):
        raise ValueError("connect_args must be a mapping")


def _freeze_value(value: Any) -> Any:
    """Convert nested containers into comparable immutable values."""
    if isinstance(value, dict):
        return tuple(sorted((str(key), _freeze_value(val)) for key, val in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_value(item) for item in value))
    return value
