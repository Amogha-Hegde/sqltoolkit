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

### 3. File-based configuration

```python
from sqltoolkit.connection import get_engine_from_file, get_async_engine_from_file

engine = get_engine_from_file(
    dialect="postgresql",
    tenant="default",
    config_path="db_config.yaml",
    access_mode="readwrite",
)

async_engine = get_async_engine_from_file(
    dialect="postgresql",
    tenant="default",
    config_path="db_config.yaml",
    access_mode="readonly",
)
```

Example YAML:

```yaml
databases:
  postgresql:
    default:
      readwrite:
        username: user
        password: password
        host: localhost
        port: 5432
        database: app
        pool_size: 10
        max_overflow: 20
        pool_pre_ping: true
      readonly:
        username: readonly
        password: password
        host: localhost
        port: 5432
        database: app
        pool_size: 5
        max_overflow: 10
        pool_pre_ping: true
```

## Notes

- Sync and async engines are cached separately.
- Readonly and readwrite engines are cached separately.
- Reusing the same registry key with different settings raises `ValueError`.
- You can still pass a full `db_url` if you prefer; structured fields are optional.
- If passwords contain reserved URL characters such as `@`, `:`, `/`, `#`, `%`, or spaces, prefer structured fields like `username` and `password` instead of a raw `db_url`. Structured config is encoded safely for you.

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
