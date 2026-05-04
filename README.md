# sqltoolkit

`sqltoolkit` is a lightweight database connection management library built on top of SQLAlchemy.

## Features

- Thread-safe engine management
- Multi-tenant database routing
- Centralized configuration
- Sync and async engine interfaces
- Separate readonly and readwrite engine registries

## Public APIs

### 1. Environment-based configuration

```python
from sqltoolkit.connection import get_engine, get_async_engine

engine = get_engine(dialect="postgresql", tenant="tenantA", access_mode="readwrite")
async_engine = get_async_engine(dialect="postgresql", tenant="tenantA", access_mode="readonly")
```

Environment variable pattern:

```text
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__DB_URL
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__DRIVER
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__USERNAME
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__PASSWORD
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__HOST
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__PORT
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__DATABASE
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__POOL_SIZE
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__MAX_OVERFLOW
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__POOL_PRE_PING
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__ECHO
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__CONNECT_ARGS
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__QUERY
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__ENGINE_OPTIONS
```

Example:

```text
SQLTOOLKIT__POSTGRESQL__TENANTA__READWRITE__USERNAME=user
SQLTOOLKIT__POSTGRESQL__TENANTA__READWRITE__PASSWORD='p@ss:/# word%'
SQLTOOLKIT__POSTGRESQL__TENANTA__READWRITE__HOST=localhost
SQLTOOLKIT__POSTGRESQL__TENANTA__READWRITE__PORT=5432
SQLTOOLKIT__POSTGRESQL__TENANTA__READWRITE__DATABASE=app

SQLTOOLKIT__POSTGRESQL__TENANTA__READONLY__USERNAME=readonly
SQLTOOLKIT__POSTGRESQL__TENANTA__READONLY__PASSWORD='r3@d:/# only%'
SQLTOOLKIT__POSTGRESQL__TENANTA__READONLY__HOST=localhost
SQLTOOLKIT__POSTGRESQL__TENANTA__READONLY__PORT=5432
SQLTOOLKIT__POSTGRESQL__TENANTA__READONLY__DATABASE=app
```

### 2. Global engine registry

```python
from sqltoolkit.connection import EngineRegistry

engine = EngineRegistry.get_engine(
    key="default",
    dialect="postgresql",
    username="user",
    password="password",
    host="localhost",
    port=5432,
    database="mydb",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    access_mode="readwrite",
)

async_engine = EngineRegistry.get_async_engine(
    key="default",
    dialect="postgresql",
    username="user",
    password="password",
    host="localhost",
    port=5432,
    database="mydb",
    access_mode="readonly",
)
```

Supported structured fields by dialect:

- `postgresql`: `username`, `password`, `host`, `port`, `database`, `driver`, `query`
- `mysql`: `username`, `password`, `host`, `port`, `database`, `driver`, `charset`, `query`
- `oracle`: `username`, `password`, `host`, `port`, `service_name`, `sid`, `database`, `dsn`, `driver`, `query`
- `mssql`: `username`, `password`, `host`, `port`, `database`, `dsn_name`, `odbc_connect`, `odbc_driver`, `driver`, `query`
- `sqlite`: `file_path`, `database`, `in_memory`, `driver`, `query`

Common file-config extras:

- `db_url` or `url`: raw SQLAlchemy database URL
- `query`: URL query parameters
- `engine_options`: SQLAlchemy `create_engine` / `create_async_engine` kwargs
- `database_options`: alias for `engine_options` in file configs

### 3. File-based configuration

```python
from sqltoolkit.connection import get_engine_from_file, get_async_engine_from_file

engine = get_engine_from_file(
    dialect="postgresql",
    tenant="default",
    config_path="db_config.json",
    access_mode="readwrite",
)

async_engine = get_async_engine_from_file(
    dialect="postgresql",
    tenant="default",
    config_path="db_config.ini",
    access_mode="readonly",
)
```

Example JSON:

```json
{
  "databases": {
    "postgresql": {
      "default": {
        "readwrite": {
          "username": "user",
          "password": "password",
          "host": "localhost",
          "port": 5432,
          "database": "app",
          "pool_size": 10,
          "max_overflow": 20,
          "pool_pre_ping": true
        },
        "readonly": {
          "username": "readonly",
          "password": "password",
          "host": "localhost",
          "port": 5432,
          "database": "app",
          "pool_size": 5,
          "max_overflow": 10,
          "pool_pre_ping": true
        }
      }
    }
  }
}
```

Example INI:

```ini
[databases.postgresql.default.readwrite]
username = user
password = password
host = localhost
port = 5432
database = app
pool_size = 10
max_overflow = 20
pool_pre_ping = true

[databases.postgresql.default.readonly]
username = readonly
password = password
host = localhost
port = 5432
database = app
pool_size = 5
max_overflow = 10
pool_pre_ping = true
```

JSON with `db_url` and database options:

```json
{
  "databases": {
    "postgresql": {
      "default": {
        "readwrite": {
          "db_url": "postgresql+psycopg://user:password@localhost:5432/app",
          "query": {
            "application_name": "sqltoolkit"
          },
          "database_options": {
            "pool_recycle": 1800,
            "pool_use_lifo": true
          }
        }
      }
    }
  }
}
```

INI with `db_url` and database options:

```ini
[databases.postgresql.default.readwrite]
db_url = postgresql+psycopg://user:password@localhost:5432/app

[databases.postgresql.default.readwrite.query]
application_name = sqltoolkit

[databases.postgresql.default.readwrite.database_options]
pool_recycle = 1800
pool_use_lifo = true
```

## Notes

- Sync and async engines are cached separately.
- Readonly and readwrite engines are cached separately.
- Reusing the same registry key with different settings raises `ValueError`.
- You can still pass a full `db_url` if you prefer; structured fields are optional.
- If passwords contain reserved URL characters such as `@`, `:`, `/`, `#`, `%`, or spaces, prefer structured fields like `username` and `password` instead of a raw `db_url`. Structured config is encoded safely for you.

## Dialect-Specific Custom Types And Functions

`sqltoolkit` can also expose dialect-specific SQLAlchemy types and SQL function helpers.

Example for Oracle:

```python
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sqltoolkit.dialects import (
    get_custom_type,
    get_dialect_function,
    get_dialect_functions,
    list_custom_types,
    list_functions,
)


class Base(DeclarativeBase):
    pass


oracle_json = get_custom_type("oracle", "json")
oracle_bool = get_custom_type("oracle", "boolean")
oracle_dt = get_custom_type("oracle", "timezone_aware_datetime", target_timezone="Asia/Kolkata")


class AuditLog(Base):
    __tablename__ = "audit_log"

    payload: Mapped[dict] = mapped_column(oracle_json)
    is_active: Mapped[bool] = mapped_column(oracle_bool)
    created_at: Mapped[str] = mapped_column(oracle_dt)


oracle_funcs = get_dialect_functions("oracle")

stmt = select(
    oracle_funcs.sysdate(),
    oracle_funcs.systimestamp(),
    oracle_funcs.json_value(AuditLog.payload, "$.event"),
)

fallback_stmt = select(get_dialect_function("oracle", "nvl", AuditLog.payload, "{}"))

print(list_custom_types("oracle"))
print(list_functions("oracle"))
```

Current Oracle custom types:

- `json`
- `boolean`
- `bool`
- `timezone_aware_datetime`
- `datetime_tz`

Current Oracle function helpers:

- `sysdate`
- `systimestamp`
- `json_value`
- `json_query`
- `json_object`
- `nvl`
- `to_char`

This registry is dialect-scoped, so additional PostgreSQL/MySQL/MSSQL/SQLite custom types and functions can be added later without changing the public API.

Repository layout for dialect extensions:

```text
sqltoolkit/dialects/<dialect>/
├── __init__.py
├── custom_fields/
│   └── ...
└── functions/
    └── ...
```

Oracle currently includes concrete implementations in those folders, and the other dialects include the same package structure so custom fields and functions can be added consistently.

## Registry Operations

```python
from sqltoolkit.connection import EngineRegistry

EngineRegistry.list_registry_keys()
EngineRegistry.get_engine_config("postgresql:tenantA:readwrite:sync")
EngineRegistry.set_max_entries(512)
EngineRegistry.get_registry_size()
EngineRegistry.get_registry_stats()
EngineRegistry.dispose_engine(key="default", access_mode="readwrite", async_mode=False)
EngineRegistry.dispose_registry_key("postgresql:tenantA:readonly:async")
EngineRegistry.dispose_all()
```

`get_registry_stats()` returns:

```python
{
    "hits": 12,
    "misses": 3,
    "evictions": 1,
    "failure_backoffs": 2,
    "creations": 2,
    "size": 2,
    "max_entries": 512,
}
```

## Operational Notes

- The registry is process-local. If a process fork is detected, inherited engine entries are cleared and disposed before reuse.
- The registry uses LRU eviction with a default cap of `256` cached engines. Override this with `EngineRegistry.set_max_entries(...)` or `SQLTOOLKIT_REGISTRY_MAX_ENTRIES`.
- Engine creation failures are cached briefly per registry key and config fingerprint. The default failure backoff is `5` seconds and can be overridden with `SQLTOOLKIT_REGISTRY_FAILURE_TTL`.
- Engine creation uses double-checked locking. Under contention, duplicate engines may be created transiently and one will be disposed immediately after registration loses the race.
