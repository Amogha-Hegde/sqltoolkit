# Example Config Notes

These sample files show the three main config buckets used by `sqltoolkit`:

- `database_options`: connection URL/query parameters for the backend or driver.
- `session_settings`: per-connection database/session settings applied when a new DBAPI connection is created.
- `engine_options`: SQLAlchemy `create_engine()` / pool configuration.

Why the JSON samples do not contain comments:

- Standard JSON does not allow comments.
- The `*.sample.json` files are intentionally kept valid so they can be copied directly.

Backend notes:

- PostgreSQL:
  - `database_options` is for connection parameters like `application_name`.
  - `session_settings` becomes `SELECT pg_catalog.set_config(...)`.
- MySQL:
  - `database_options` is typically for URL/query values like `charset`.
  - `session_settings` becomes `SET SESSION ...`.
- Oracle:
  - `session_settings` becomes `ALTER SESSION SET ...`.
- MSSQL:
  - `session_settings` becomes `SET ...`.
  - String values are emitted as raw T-SQL tokens, so values like `READ COMMITTED` should be written exactly as intended.
- SQLite:
  - `session_settings` becomes `PRAGMA ...`.
