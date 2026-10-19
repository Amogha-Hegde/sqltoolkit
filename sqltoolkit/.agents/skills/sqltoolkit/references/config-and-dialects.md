# Config And Dialects Reference

## Access modes

Valid access modes:

- `readwrite`
- `readonly`

Default access mode is `readwrite`.

Normalization should stay strict. Invalid values raise `ValueError`.

## Config entry points

`sqltoolkit.connection.config` supports three main config sources:

- env vars via `load_config_from_env(...)`
- config files via `load_config_from_file(...)`
- direct keyword arguments via `config_from_kwargs(...)`

`config_from_kwargs(...)` requires either:

- `db_url`, or
- `dialect`

## Supported engine-level options

These are treated as generic engine settings rather than dialect fields:

- `driver`
- `pool_size`
- `max_overflow`
- `pool_pre_ping`
- `echo`
- `connect_args`
- `query`
- `engine_options`

## Environment variable pattern

Prefix format:

`SQLTOOLKIT__{DIALECT}__{TENANT}__{ACCESS_MODE}__...`

Common suffixes include:

- `DB_URL`
- `DRIVER`
- `USERNAME`
- `USER`
- `PASSWORD`
- `HOST`
- `PORT`
- `DATABASE`
- `DBNAME`
- `FILE_PATH`
- `SERVICE_NAME`
- `SID`
- `DSN`
- `DSN_NAME`
- `ODBC_CONNECT`
- `ODBC_DRIVER`
- `CHARSET`
- `POOL_SIZE`
- `MAX_OVERFLOW`
- `POOL_PRE_PING`
- `ECHO`
- `CONNECT_ARGS`
- `QUERY`
- `ENGINE_OPTIONS`
- `IN_MEMORY`

JSON-bearing fields such as `CONNECT_ARGS`, `QUERY`, and `ENGINE_OPTIONS` should decode to mappings.

## File config shape

Expected structure:

```yaml
databases:
  <dialect>:
    <tenant>:
      <access_mode>:
        ...
```

Supported file formats:

- YAML
- JSON

## Dialect field summary

### PostgreSQL

Common structured fields:

- `username`
- `password`
- `host`
- `port`
- `database`
- `driver`
- `query`

### MySQL

Common structured fields:

- `username`
- `password`
- `host`
- `port`
- `database`
- `driver`
- `charset`
- `query`

### Oracle

Common structured fields:

- `username`
- `password`
- `host`
- `port`
- `service_name`
- `sid`
- `database`
- `dsn`
- `driver`
- `query`

Oracle changes may also affect connect-arg handling, so inspect the dialect helpers before editing.

### MSSQL

Common structured fields:

- `username`
- `password`
- `host`
- `port`
- `database`
- `dsn_name`
- `odbc_connect`
- `odbc_driver`
- `driver`
- `query`

### SQLite

Common structured fields:

- `file_path`
- `database`
- `in_memory`
- `driver`
- `query`

## Editing guidance

- Treat repository code as canonical if a reference file and implementation disagree.
- For behavior changes, update examples in `../../../../../README.md`.
- When adding new dialect fields, update parsing, URL construction, and public docs together.
