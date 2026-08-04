# sqltoolkit

`sqltoolkit` is a lightweight database connection management library built on top of SQLAlchemy.

## Features

- Thread-safe engine management
- Multi-tenant database routing
- Centralized configuration
- Sync and async engine interfaces
- Separate engine caches by tenant, alias, and sync/async interface

## Public APIs

### 1. Environment-based configuration

```python
from sqltoolkit.connection import get_engine, get_async_engine

engine = get_engine(dialect="postgresql", tenant="tenantA", access_mode="primary")
async_engine = get_async_engine(dialect="postgresql", tenant="tenantA", access_mode="replica")
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
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__DATABASE_OPTIONS
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__SESSION_SETTINGS
SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__ENGINE_OPTIONS
```

`ACCESS_MODE` is an alias segment, not a fixed enum. Use names that match your deployment
shape, such as `primary`, `replica`, `analytics`, `migration`, or `tenant_admin`.
Aliases are normalized by trimming whitespace and lowercasing.

Example:

```text
SQLTOOLKIT__POSTGRESQL__TENANTA__PRIMARY__USERNAME=user
SQLTOOLKIT__POSTGRESQL__TENANTA__PRIMARY__PASSWORD='p@ss:/# word%'
SQLTOOLKIT__POSTGRESQL__TENANTA__PRIMARY__HOST=localhost
SQLTOOLKIT__POSTGRESQL__TENANTA__PRIMARY__PORT=5432
SQLTOOLKIT__POSTGRESQL__TENANTA__PRIMARY__DATABASE=app

SQLTOOLKIT__POSTGRESQL__TENANTA__REPLICA__USERNAME=replica
SQLTOOLKIT__POSTGRESQL__TENANTA__REPLICA__PASSWORD='r3@d:/# only%'
SQLTOOLKIT__POSTGRESQL__TENANTA__REPLICA__HOST=localhost
SQLTOOLKIT__POSTGRESQL__TENANTA__REPLICA__PORT=5432
SQLTOOLKIT__POSTGRESQL__TENANTA__REPLICA__DATABASE=app
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
    access_mode="primary",
)

async_engine = EngineRegistry.get_async_engine(
    key="default",
    dialect="postgresql",
    username="user",
    password="password",
    host="localhost",
    port=5432,
    database="mydb",
    access_mode="replica",
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
- `database_options`: database URL/query parameters such as PostgreSQL `application_name`
- `query`: alias for `database_options`
- `session_settings`: backend session settings applied when a new DBAPI connection is created
- `engine_options`: SQLAlchemy `create_engine` / `create_async_engine` kwargs
- `options`: alias for `engine_options` in file configs

### 3. File-based configuration

```python
from sqltoolkit.connection import get_engine_from_file, get_async_engine_from_file

engine = get_engine_from_file(
    dialect="postgresql",
    tenant="default",
    config_path="db_config.json",
    access_mode="primary",
)

async_engine = get_async_engine_from_file(
    dialect="postgresql",
    tenant="default",
    config_path="db_config.ini",
    access_mode="replica",
)
```

Example JSON:

```json
{
  "databases": {
    "postgresql": {
      "default": {
        "primary": {
          "username": "user",
          "password": "password",
          "host": "localhost",
          "port": 5432,
          "database": "app",
          "pool_size": 10,
          "max_overflow": 20,
          "pool_pre_ping": true
        },
        "replica": {
          "username": "replica",
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
[databases.postgresql.default.primary]
username = user
password = password
host = localhost
port = 5432
database = app
pool_size = 10
max_overflow = 20
pool_pre_ping = true

[databases.postgresql.default.replica]
username = replica
password = password
host = localhost
port = 5432
database = app
pool_size = 5
max_overflow = 10
pool_pre_ping = true
```

JSON with `db_url`, database options, and SQLAlchemy engine options:

```json
{
  "databases": {
    "postgresql": {
      "default": {
        "primary": {
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
}
```

INI with `db_url`, database options, and SQLAlchemy engine options:

```ini
[databases.postgresql.default.primary]
db_url = postgresql+psycopg://user:password@localhost:5432/app

[databases.postgresql.default.primary.database_options]
application_name = sqltoolkit

[databases.postgresql.default.primary.engine_options]
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
      "default": {
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
}
```

PostgreSQL sample INI:

```ini
[databases.postgresql.default.primary]
db_url = postgresql+psycopg://user:password@localhost:5432/app

[databases.postgresql.default.primary.database_options]
application_name = sqltoolkit

[databases.postgresql.default.primary.session_settings]
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

[databases.postgresql.default.primary.engine_options]
pool_recycle = 1800
pool_use_lifo = true
```

MySQL sample JSON:

```json
{
  "databases": {
    "mysql": {
      "default": {
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
}
```

MySQL sample INI:

```ini
[databases.mysql.default.primary]
db_url = mysql+pymysql://user:password@localhost:3306/app

[databases.mysql.default.primary.session_settings]
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
      "default": {
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
}
```

Oracle sample INI:

```ini
[databases.oracle.default.primary]
username = user
password = password
host = localhost
port = 1521
service_name = FREEPDB1

[databases.oracle.default.primary.session_settings]
time_zone = UTC
nls_date_format = YYYY-MM-DD
nls_timestamp_format = YYYY-MM-DD HH24:MI:SS
```

MSSQL sample JSON:

```json
{
  "databases": {
    "mssql": {
      "default": {
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
}
```

MSSQL sample INI:

```ini
[databases.mssql.default.primary]
db_url = mssql+pyodbc://user:password@localhost:1433/app?driver=ODBC+Driver+18+for+SQL+Server

[databases.mssql.default.primary.session_settings]
LOCK_TIMEOUT = 5000
XACT_ABORT = true
TRANSACTION ISOLATION LEVEL = READ COMMITTED
```

SQLite sample JSON:

```json
{
  "databases": {
    "sqlite": {
      "default": {
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
}
```

SQLite sample INI:

```ini
[databases.sqlite.default.primary]
file_path = ./app.db

[databases.sqlite.default.primary.session_settings]
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

Sample configuration files for every supported dialect are available in [examples/configs](/Users/amogha/PycharmProjects/sqltoolkit/examples/configs). Commentary for those examples is in [examples/configs/README.md](/Users/amogha/PycharmProjects/sqltoolkit/examples/configs/README.md).

Sample environment files for every supported dialect are available in [examples/env-sample](/Users/amogha/PycharmProjects/sqltoolkit/examples/env-sample). Notes for those examples are in [examples/env-sample/README.md](/Users/amogha/PycharmProjects/sqltoolkit/examples/env-sample/README.md).

## Registry Operations

```python
from sqltoolkit.connection import EngineRegistry

EngineRegistry.list_registry_keys()
EngineRegistry.get_engine_config("postgresql:tenantA:primary:sync")
EngineRegistry.set_max_entries(512)
EngineRegistry.get_registry_size()
EngineRegistry.get_registry_stats()
EngineRegistry.dispose_engine(key="default", access_mode="primary", async_mode=False)
EngineRegistry.dispose_registry_key("postgresql:tenantA:replica:async")
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
