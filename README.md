# sqltoolkit

`sqltoolkit` is a lightweight database connection management library built on top of SQLAlchemy.

## Features

- Thread-safe engine management
- Alias-based database routing
- Centralized configuration
- Sync and async engine interfaces
- Separate engine caches by alias and sync/async interface

SQLAlchemy 2.1 is supported. It requires Python 3.11 or newer; on older supported Python versions, package installers select a compatible SQLAlchemy 2.0 release. SQLAlchemy 2.1 no longer installs `greenlet` by default. SQLToolkit includes SQLAlchemy's `asyncio` extra as a base dependency because it exposes async APIs from the package:

```bash
pip install "sqltoolkit[postgresql]"
```

Replace `postgresql` with the driver extra for your database (`mysql`, `oracle`, `mssql`, or `sqlite`). The `all` extra installs all supported database drivers.

## Public APIs

### 1. File-based configuration

```python
from sqltoolkit import get_engine, get_async_engine

engine = get_engine(alias="test")
async_engine = get_async_engine(alias="test")
```

By default, these use `dialect="postgresql"` and `config_path="db_config.json"`.
Override either value when needed:

```python
from sqltoolkit import get_engine

engine = get_engine(
    alias="test",
    dialect="sqlite",
    config_path="sqlite_config.ini",
)
```

The file config shape is:

```json
{
  "databases": {
    "postgresql": {
      "test": {
        "db_url": "postgresql+psycopg://user:password@localhost:5432/app"
      }
    }
  }
}
```

`alias` is the only routing name. Use aliases that match your app, such as
`test`, `primary`, `replica`, `analytics`, or `migration`. Aliases are normalized
by trimming whitespace and lowercasing.

### 2. Environment-based configuration

```python
from sqltoolkit import get_engine_from_env, get_async_engine_from_env

engine = get_engine_from_env(alias="test")
async_engine = get_async_engine_from_env(alias="test")
```

Environment variable pattern:

```text
SQLTOOLKIT__{DIALECT}__{ALIAS}__DB_URL
SQLTOOLKIT__{DIALECT}__{ALIAS}__DRIVER
SQLTOOLKIT__{DIALECT}__{ALIAS}__USERNAME
SQLTOOLKIT__{DIALECT}__{ALIAS}__PASSWORD
SQLTOOLKIT__{DIALECT}__{ALIAS}__HOST
SQLTOOLKIT__{DIALECT}__{ALIAS}__PORT
SQLTOOLKIT__{DIALECT}__{ALIAS}__DATABASE
SQLTOOLKIT__{DIALECT}__{ALIAS}__POOL_SIZE
SQLTOOLKIT__{DIALECT}__{ALIAS}__MAX_OVERFLOW
SQLTOOLKIT__{DIALECT}__{ALIAS}__POOL_PRE_PING
SQLTOOLKIT__{DIALECT}__{ALIAS}__ECHO
SQLTOOLKIT__{DIALECT}__{ALIAS}__CONNECT_ARGS
SQLTOOLKIT__{DIALECT}__{ALIAS}__QUERY
SQLTOOLKIT__{DIALECT}__{ALIAS}__DATABASE_OPTIONS
SQLTOOLKIT__{DIALECT}__{ALIAS}__SESSION_SETTINGS
SQLTOOLKIT__{DIALECT}__{ALIAS}__ENGINE_OPTIONS
```

Example:

```text
SQLTOOLKIT__POSTGRESQL__TEST__USERNAME=user
SQLTOOLKIT__POSTGRESQL__TEST__PASSWORD='p@ss:/# word%'
SQLTOOLKIT__POSTGRESQL__TEST__HOST=localhost
SQLTOOLKIT__POSTGRESQL__TEST__PORT=5432
SQLTOOLKIT__POSTGRESQL__TEST__DATABASE=app
```

### 3. Global engine registry

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
)

async_engine = EngineRegistry.get_async_engine(
    key="default",
    dialect="postgresql",
    username="user",
    password="password",
    host="localhost",
    port=5432,
    database="mydb",
)
```

### Using synchronous and asynchronous connections

An engine is a process-local connection pool. Getting an engine does not usually open a database connection; SQLAlchemy checks out a pooled connection when you connect or run a query. Use the matching sync or async API for your application.

Engine getters such as `get_engine()`, `get_async_engine()`, `get_engine_from_env()`, and the `EngineRegistry.get_engine()` methods are designed to be called repeatedly with the same key/alias and configuration: they return the cached engine. Reuse the engine for the lifetime of the application rather than creating one per request or query. Calling with the same registry key but different settings raises `ValueError`. File- and environment-based getters key the cache by dialect, alias, and sync/async mode, so use a stable alias for each database role.

For a direct connection, use a context manager so the connection returns to the pool when the block ends:

```python
from sqltoolkit import get_engine, get_async_engine

# Synchronous
engine = get_engine(alias="primary", dialect="postgresql", config_path="db_config.json")
with engine.connect() as connection:
    rows = connection.exec_driver_sql("SELECT 1").all()

# Asynchronous (use an async driver in the configured URL)
async_engine = get_async_engine(
    alias="primary", dialect="postgresql", config_path="db_config.json"
)

async def fetch_value() -> int:
    async with async_engine.connect() as connection:
        result = await connection.exec_driver_sql("SELECT 1")
        return result.scalar_one()
```

For ORM work, create a session per unit of work. Sessions and checked-out connections should not be shared between concurrent threads or async tasks. The session factories below are cached; each call creates a fresh session:

```python
from sqltoolkit.connection import EngineRegistry
from sqltoolkit import get_engine, get_async_engine

sync_engine = get_engine(alias="primary", config_path="db_config.json")
SyncSession = EngineRegistry.get_sessionmaker(
    key="primary", engine=sync_engine, expire_on_commit=False
)

with SyncSession.begin() as session:
    # session.add(...), session.execute(...)
    ...

async_engine = get_async_engine(alias="primary", config_path="db_config.json")
AsyncSession = EngineRegistry.get_async_sessionmaker(
    key="primary", engine=async_engine, expire_on_commit=False
)

async def update_data() -> None:
    async with AsyncSession.begin() as session:
        # await session.execute(...)
        ...
```

`Session.begin()` and `AsyncSession.begin()` commit on successful exit and roll back if an exception occurs. If you use `session_factory()` or `async_session_factory()` to get an individual session, close it with `with session:` or `async with session:` (or call `close()` / `await close()`) so checked-out connections are returned promptly. Dispose engines during application shutdown when they are no longer needed; async applications should use SQLAlchemy's `await async_engine.dispose()`.

Reuse guidance:

- **Call repeatedly:** engine getters, `EngineRegistry.get_sessionmaker()`, and `EngineRegistry.get_async_sessionmaker()` with the same key, engine, and options. The getters return cached objects. Calling `SessionMaker()` or `AsyncSessionMaker()` repeatedly is also expected; each call returns a new session.
- **Use briefly, then close:** each `engine.connect()` / `async_engine.connect()` checkout and each `Session` / `AsyncSession`. Do not keep them in global variables or share them between concurrent work. Context managers close them when the block ends.
- **Call at shutdown or when retiring a database:** `engine.dispose()` / `await async_engine.dispose()` releases the pool's connections. The engine object can open new connections after disposal, so disposal is cleanup, not a permanent invalidation. `EngineRegistry.dispose_engine(...)` removes the cached entry; the next getter call can create a new engine. Use `EngineRegistry.dispose_all()` outside an event loop, or `await EngineRegistry.adispose_all()` in async code. These are intended for application shutdown or tests, not for each request.

Supported structured fields by dialect:

- `postgresql`: `username`, `password`, `host`, `port`, `database`, `driver`, `query`
- `mysql`: `username`, `password`, `host`, `port`, `database`, `driver`, `charset`, `query`
- `oracle`: `username`, `password`, `host`, `port`, `service_name`, `sid`, `database`, `dsn`, `driver`, `query`
- `mssql`: `username`, `password`, `host`, `port`, `database`, `dsn_name`, `odbc_connect`, `odbc_driver`, `driver`, `query`
- `sqlite`: `file_path`, `database`, `in_memory`, `driver`, `query`

Common file-config extras:

- `db_url` or `url`: raw SQLAlchemy database URL
- `database_options`: database URL/query parameters such as PostgreSQL `application_name`
- `query`: alias for `database_options`
- `session_settings`: backend session settings applied when a new DBAPI connection is created
- `engine_options`: SQLAlchemy `create_engine` / `create_async_engine` kwargs
- `options`: alias for `engine_options` in file configs

### 4. Explicit file helpers

```python
from sqltoolkit.connection import get_engine_from_file, get_async_engine_from_file

engine = get_engine_from_file(
    alias="test",
    dialect="postgresql",
    config_path="db_config.json",
)

async_engine = get_async_engine_from_file(
    alias="test",
    dialect="postgresql",
    config_path="db_config.ini",
)
```

Example JSON:

```json
{
  "databases": {
    "postgresql": {
      "test": {
        "username": "user",
        "password": "password",
        "host": "localhost",
        "port": 5432,
        "database": "app",
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": true
      }
    }
  }
}
```

Example INI:

```ini
[databases.postgresql.test]
username = user
password = password
host = localhost
port = 5432
database = app
pool_size = 10
max_overflow = 20
pool_pre_ping = true
```

JSON with `db_url`, database options, and SQLAlchemy engine options:

```json
{
  "databases": {
    "postgresql": {
      "test": {
        "db_url": "postgresql+psycopg://user:password@localhost:5432/app",
        "database_options": {
          "application_name": "sqltoolkit"
        },
        "engine_options": {
          "pool_recycle": 1800,
          "pool_use_lifo": true
        }
      }
    }
  }
}
```

INI with `db_url`, database options, and SQLAlchemy engine options:

```ini
[databases.postgresql.primary]
db_url = postgresql+psycopg://user:password@localhost:5432/app

[databases.postgresql.primary.database_options]
application_name = sqltoolkit

[databases.postgresql.primary.engine_options]
pool_recycle = 1800
pool_use_lifo = true
```

Structured session settings by backend:

- PostgreSQL: `session_settings` becomes `SELECT pg_catalog.set_config(...)`
- MySQL: `session_settings` becomes `SET SESSION ...`
- Oracle: `session_settings` becomes `ALTER SESSION SET ...`
- MSSQL: `session_settings` becomes `SET ...`; string values are emitted as raw T-SQL tokens, so values like `READ COMMITTED` should be written exactly as intended
- SQLite: `session_settings` becomes `PRAGMA ...`

PostgreSQL sample JSON:

```json
{
  "databases": {
    "postgresql": {
      "primary": {
        "db_url": "postgresql+psycopg://user:password@localhost:5432/app",
        "database_options": {
          "application_name": "sqltoolkit"
        },
        "session_settings": {
          "search_path": "app, public",
          "statement_timeout": "30000",
          "lock_timeout": "5000",
          "idle_in_transaction_session_timeout": "60000",
          "deadlock_timeout": "1000",
          "default_transaction_isolation": "read committed",
          "default_transaction_read_only": false,
          "default_transaction_deferrable": false,
          "jit": false,
          "max_parallel_workers_per_gather": 2,
          "work_mem": "64MB",
          "maintenance_work_mem": "256MB",
          "random_page_cost": 1.1,
          "effective_cache_size": "4GB",
          "log_min_duration_statement": 250,
          "TimeZone": "UTC",
          "DateStyle": "ISO, MDY",
          "row_security": true
        },
        "engine_options": {
          "pool_recycle": 1800,
          "pool_use_lifo": true
        }
      }
    }
  }
}
```

PostgreSQL sample INI:

```ini
[databases.postgresql.primary]
db_url = postgresql+psycopg://user:password@localhost:5432/app

[databases.postgresql.primary.database_options]
application_name = sqltoolkit

[databases.postgresql.primary.session_settings]
search_path = app, public
statement_timeout = 30000
lock_timeout = 5000
idle_in_transaction_session_timeout = 60000
deadlock_timeout = 1000
default_transaction_isolation = read committed
default_transaction_read_only = false
default_transaction_deferrable = false
jit = false
max_parallel_workers_per_gather = 2
work_mem = 64MB
maintenance_work_mem = 256MB
random_page_cost = 1.1
effective_cache_size = 4GB
log_min_duration_statement = 250
TimeZone = UTC
DateStyle = ISO, MDY
row_security = true

[databases.postgresql.primary.engine_options]
pool_recycle = 1800
pool_use_lifo = true
```

MySQL sample JSON:

```json
{
  "databases": {
    "mysql": {
      "primary": {
        "db_url": "mysql+pymysql://user:password@localhost:3306/app",
        "session_settings": {
          "sql_mode": "STRICT_ALL_TABLES",
          "time_zone": "+00:00",
          "innodb_lock_wait_timeout": 10,
          "max_execution_time": 5000
        }
      }
    }
  }
}
```

MySQL sample INI:

```ini
[databases.mysql.primary]
db_url = mysql+pymysql://user:password@localhost:3306/app

[databases.mysql.primary.session_settings]
sql_mode = STRICT_ALL_TABLES
time_zone = +00:00
innodb_lock_wait_timeout = 10
max_execution_time = 5000
```

Oracle sample JSON:

```json
{
  "databases": {
    "oracle": {
      "primary": {
        "username": "user",
        "password": "password",
        "host": "localhost",
        "port": 1521,
        "service_name": "FREEPDB1",
        "session_settings": {
          "time_zone": "UTC",
          "nls_date_format": "YYYY-MM-DD",
          "nls_timestamp_format": "YYYY-MM-DD HH24:MI:SS"
        }
      }
    }
  }
}
```

Oracle sample INI:

```ini
[databases.oracle.primary]
username = user
password = password
host = localhost
port = 1521
service_name = FREEPDB1

[databases.oracle.primary.session_settings]
time_zone = UTC
nls_date_format = YYYY-MM-DD
nls_timestamp_format = YYYY-MM-DD HH24:MI:SS
```

MSSQL sample JSON:

```json
{
  "databases": {
    "mssql": {
      "primary": {
        "db_url": "mssql+pyodbc://user:password@localhost:1433/app?driver=ODBC+Driver+18+for+SQL+Server",
        "session_settings": {
          "LOCK_TIMEOUT": 5000,
          "XACT_ABORT": true,
          "TRANSACTION ISOLATION LEVEL": "READ COMMITTED"
        }
      }
    }
  }
}
```

MSSQL sample INI:

```ini
[databases.mssql.primary]
db_url = mssql+pyodbc://user:password@localhost:1433/app?driver=ODBC+Driver+18+for+SQL+Server

[databases.mssql.primary.session_settings]
LOCK_TIMEOUT = 5000
XACT_ABORT = true
TRANSACTION ISOLATION LEVEL = READ COMMITTED
```

SQLite sample JSON:

```json
{
  "databases": {
    "sqlite": {
      "primary": {
        "file_path": "./app.db",
        "session_settings": {
          "foreign_keys": true,
          "journal_mode": "WAL",
          "busy_timeout": 5000
        }
      }
    }
  }
}
```

SQLite sample INI:

```ini
[databases.sqlite.primary]
file_path = ./app.db

[databases.sqlite.primary.session_settings]
foreign_keys = true
journal_mode = WAL
busy_timeout = 5000
```

## Notes

- Sync and async engines are cached separately.
- Different aliases are cached separately.
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

Sample configuration files for every supported dialect are available in [examples/configs](examples/configs). Commentary for those examples is in [examples/configs/README.md](examples/configs/README.md).

Sample environment files for every supported dialect are available in [examples/env-sample](examples/env-sample). Notes for those examples are in [examples/env-sample/README.md](examples/env-sample/README.md).

## Registry Operations

```python
from sqltoolkit.connection import EngineRegistry

EngineRegistry.list_registry_keys()
EngineRegistry.get_engine_config("postgresql:test:sync")
EngineRegistry.set_max_entries(512)
EngineRegistry.get_registry_size()
EngineRegistry.get_registry_stats()
EngineRegistry.dispose_engine(key="default", async_mode=False)
EngineRegistry.dispose_all()
```

When disposing async engines from within an active event loop, use the async cleanup methods:

```python
await EngineRegistry.adispose_registry_key("postgresql:test:async")
await EngineRegistry.adispose_all()
await EngineRegistry.adispose_engine(key="default", async_mode=True)
```

The synchronous `dispose_all()` method runs async engine disposal when called outside an event loop. It raises a clear error inside a running loop so async connections are not closed through SQLAlchemy's synchronous proxy.

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
- Engine construction and database connection establishment failures are cached briefly per registry key and config fingerprint. The default failure backoff is `5` seconds and can be overridden with `SQLTOOLKIT_REGISTRY_FAILURE_TTL`.
- Failure records use process-local memory by default. Set `SQLTOOLKIT_FAILURE_BACKEND=none` to disable failure caching. Supported values are `memory` and `none`.
- Engine creation uses double-checked locking. Under contention, duplicate engines may be created transiently and one will be disposed immediately after registration loses the race.
